"""Join a finished strict Claude Single study with the retained three conditions."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from benchmarks.kramabench._io import write_json
from scripts.kramabench.results import formatted, summarize


def compare(baseline, single_run, output, expected_tasks=104):
    baseline, root, output = (Path(p).resolve() for p in (baseline, single_run, output))
    if output.exists() or output.is_relative_to(root) or root.is_relative_to(output):
        raise ValueError("Use a fresh comparison outside native run evidence")
    base_bytes, native_bytes = baseline.read_bytes(), (root/"summary.json").read_bytes()
    base, native = json.loads(base_bytes), json.loads(native_bytes)
    if json.loads((root/"progress.json").read_text()).get("stage") != "finished":
        raise ValueError("Claude Single workload is not finished")
    if native["plan"]["scoring"] != base["scoring"]:
        raise ValueError("Scoring contract differs")
    backends = ("deepagents", "claude-code-agent-team", "claude-code-subagents")
    task_sets = [{r["task_id"] for r in base["rows"] if r["backend"] == b} for b in backends]
    if (len(base["rows"]) != 3*expected_tasks or any(len(s) != expected_tasks or s != task_sets[0] for s in task_sets)
            or not {"single", "team", "subagents"} <= base["cohorts"].keys()):
        raise ValueError("Expected the complete matched three-condition baseline")
    if len(native["rows"]) != expected_tasks or {r["task_id"] for r in native["rows"]} != task_sets[0]:
        raise ValueError("Claude Single task set differs")
    rows = []
    for original in native["rows"]:
        if original["backend"] != "claude-code-single-agent":
            raise ValueError("Wrong native condition")
        grade = original.get("effective_grade", original["grade"])
        path = root/original["task_id"]/original["backend"]/"submission.json"
        actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
        if path.is_symlink() or actual != grade["submission_file_sha256"] or grade["scoring_contract"] != base["scoring"]:
            raise ValueError("Grade is not bound to the frozen scoring contract and artifact")
        audit = original.get("single_agent_audit", {})
        if (not audit.get("passed") or audit.get("subagent_starts") != 0
                or audit.get("executed_delegation_tools") != 0
                or original.get("single_agent_transcript_audit", {}).get("member_messages") != 0):
            raise ValueError("Missing strict Single proof; do not label unverified execution as Single")
        row = dict(original, grade=grade, source_run=str(root), replacement=None)
        row.pop("effective_grade", None)
        rows.append(row)
    stats = summarize(rows)
    stats["native_single_policy_passes"] = sum(r["single_agent_audit"]["passed"] for r in rows)
    stats["native_subagent_starts"] = sum(r["single_agent_audit"]["subagent_starts"] for r in rows)
    result = dict(base, cohorts=dict(base["cohorts"], claude_single=stats), rows=base["rows"]+rows,
        source_previous_comparison=dict(path=str(baseline), sha256=hashlib.sha256(base_bytes).hexdigest()),
        source_claude_single=dict(path=str(root/"summary.json"), sha256=hashlib.sha256(native_bytes).hexdigest()),
        claude_single_billing=native.get("billing"), claude_single_judge_billing=native.get("judge_billing"),
        new_solver_calls=0, new_judge_calls=0,
        limitation="Team is 99 original + 5 repaired. Native modes/tool policies/prompts differ. Descriptive, not causal; unknown accounting is not zero.")
    output.mkdir(parents=True, exist_ok=False)
    write_json(output/"summary.json", result)
    groups = [result["cohorts"][k] for k in ("single", "claude_single", "subagents", "team")]
    lines = ["# Deep Agents Single / Claude Single / Claude Subagents / Claude Agent Team", "",
             "| Metric | Deep Agents Single | Claude Single | Claude Subagents | Claude Agent Team |",
             "| --- | ---: | ---: | ---: | ---: |"]
    for title, field, spec in (("Binary accuracy (84 tasks)", "binary_accuracy", ".2%"),
                               ("Mean CLI seconds", "mean_cli_seconds", ".1f"),
                               ("Cache reuse", "token_weighted_cache_hit_rate", ".2%")):
        lines.append("| "+title+" | "+" | ".join(formatted(g[field], spec) for g in groups)+" |")
    lines.append("| Matching offline replay | "+" | ".join(str(g["replay_pass"])+"/"+str(expected_tasks) for g in groups)+" |")
    for kind in groups[0]["metrics"]:
        lines.append("| "+kind+" | "+" | ".join(formatted(g["metrics"][kind]["mean"], ".6f") for g in groups)+" |")
    lines += ["", "Solver retained-message USD estimates (off-peak / peak; not actual bills):", ""]
    for name, g in zip(("Deep Agents Single", "Claude Single", "Claude Subagents", "Claude Agent Team"), groups):
        cost = g["selected_artifact_visible_cost"]
        lines.append("- "+name+": "+formatted(cost["estimated_usd_off_peak"], ".6f")+" / "+formatted(cost["estimated_usd_peak"], ".6f"))
    lines += ["", "Claude Single account solver interval: "+json.dumps(result["claude_single_billing"])+".",
              "Claude Single account judge interval: "+json.dumps(result["claude_single_judge_billing"])+".",
              "", "Account intervals may include other account use; displayed zero is not proof of free judging.",
              "", result["limitation"], ""]
    (output/"REPORT.md").write_text("\n".join(lines))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--single-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(compare(args.baseline, args.single_run, args.output)["cohorts"]))


if __name__ == "__main__":
    main()
