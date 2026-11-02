"""Fail-closed preflight for two real experimental arms, before model dispatch."""

from pathlib import Path
from .catalog import fingerprint
from .container_contract import overlaps, validate_artifact_paths


def selected_conditions(mode, leader_mode=None):
    """Explicit arm selection; never silently expands the number of paid attempts."""
    if leader_mode not in {None, "full", "coordinator"}:
        raise ValueError("Unknown Leader mode")
    if mode == "leader-pair":
        if leader_mode is not None:
            raise ValueError("leader-pair already selects coordinator and full; omit --leader-mode")
        return {"team_coordinator": dict(mode="team", leader_mode="coordinator"),
                "team_full": dict(mode="team", leader_mode="full")}
    if mode not in {"single", "team", "both"}:
        raise ValueError("Unknown comparison mode")
    if mode == "single" and leader_mode not in {None, "full"}:
        raise ValueError("--leader-mode only applies to a selected Team arm")
    names = ("single", "team") if mode == "both" else (mode,)
    return {name: dict(mode=name, leader_mode=(leader_mode or "coordinator") if name == "team" else "full") for name in names}


def validate_pair(arms):
    if set(arms) == {"team_coordinator", "team_full"}:
        expected = selected_conditions("leader-pair")
        if any(arms[name].get("condition") != condition for name, condition in expected.items()):
            raise ValueError("Leader contrast requires coordinator and full Team conditions")
        single, team = (arms[name] for name in expected)
        contrast = "leader_permissions"
    elif set(arms) == {"single", "team"}:
        single, team = arms["single"], arms["team"]
        contrast = "single_vs_team"
    else:
        raise ValueError("Exactly single/team or team_coordinator/team_full arms are required")
    if single["contract"] != team["contract"]:
        raise ValueError("Task/model/tool/prompt/budget/pricing/source comparison contract differs")
    required = {"task", "model", "tools", "common_prompt", "budgets", "pricing", "source_digest"}
    if not required <= single["contract"].keys():
        raise ValueError("Incomplete comparison contract")
    first, second = single["environment"], team["environment"]
    for key in ("image_id", "dataset_files", "resources", "network"):
        if first[key] != second[key]:
            raise ValueError("Comparison environments differ: " + key)
    if first["container_id"] == second["container_id"]:
        raise ValueError("Comparison arms must use different containers")
    work_roots = []
    for arm in (single, team):
        mounts = {m["Destination"]: m for m in arm["environment"]["mounts"]}
        work_roots.append(Path(mounts["/workspace"]["Source"]).resolve())
    if overlaps(*work_roots):
        raise ValueError("Comparison workspaces overlap")
    for arm in (single, team):
        mounts = {m["Destination"]: m for m in arm["environment"]["mounts"]}
        validate_artifact_paths(mounts["/data"]["Source"], arm["output"], arm["archive"], work_roots=work_roots)
        if Path(arm["output"]).exists() or Path(arm["archive"]).exists():
            raise ValueError("Comparison output and archive paths must be fresh")
    if any(overlaps(single[a], team[b]) for a in ("output", "archive") for b in ("output", "archive")):
        raise ValueError("Comparison evidence namespaces overlap")
    record = {"contrast": contrast, "contract": single["contract"], "arms": arms}
    return dict(record, sha256=fingerprint(record))
