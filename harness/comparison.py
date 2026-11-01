"""Fail-closed preflight for two real experimental arms, before model dispatch."""

from pathlib import Path
from .catalog import fingerprint
from .container_contract import overlaps, validate_artifact_paths


def validate_pair(arms):
    if set(arms) != {"single", "mas"}:
        raise ValueError("Exactly single and mas arms are required")
    single, mas = arms["single"], arms["mas"]
    if single["contract"] != mas["contract"]:
        raise ValueError("Task/model/tool/prompt/budget/pricing/source comparison contract differs")
    required = {"task", "model", "tools", "common_prompt", "budgets", "pricing", "source_digest"}
    if not required <= single["contract"].keys():
        raise ValueError("Incomplete comparison contract")
    first, second = single["environment"], mas["environment"]
    for key in ("image_id", "dataset_files", "resources", "network"):
        if first[key] != second[key]:
            raise ValueError("Comparison environments differ: " + key)
    if first["container_id"] == second["container_id"]:
        raise ValueError("Comparison arms must use different containers")
    work_roots = []
    for arm in (single, mas):
        mounts = {m["Destination"]: m for m in arm["environment"]["mounts"]}
        work_roots.append(Path(mounts["/workspace"]["Source"]).resolve())
    if overlaps(*work_roots):
        raise ValueError("Comparison workspaces overlap")
    for arm in (single, mas):
        mounts = {m["Destination"]: m for m in arm["environment"]["mounts"]}
        validate_artifact_paths(mounts["/data"]["Source"], arm["output"], arm["archive"], work_roots=work_roots)
        if Path(arm["output"]).exists() or Path(arm["archive"]).exists():
            raise ValueError("Comparison output and archive paths must be fresh")
    if any(overlaps(single[a], mas[b]) for a in ("output", "archive") for b in ("output", "archive")):
        raise ValueError("Comparison evidence namespaces overlap")
    record = {"contract": single["contract"], "arms": arms}
    return dict(record, sha256=fingerprint(record))
