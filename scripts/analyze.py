"""Summarize output directories: success, cost, paired tests, loss diagnostics, P1-P4.

  .venv/bin/python scripts/analyze.py outputs/bcp-phase0 outputs/tau2-phase0

BrowseComp-Plus success needs grades (scripts/grade_bcp.py). Error and
ungraded runs are counted apart and never treated as wrong answers. Writes
summary.json into each directory and criteria.json next to the first one.
No model calls.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from statistics import mean

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mas_info.analysis import criteria, stats
from mas_info.bcp import diagnostics as bcp_diag
from mas_info.bcp.data import load_qrels, load_tasks
from mas_info.config import ROOT, load_config, resolve
from mas_info.runner import write_json
from mas_info.tau import diagnostics as tau_diag
from mas_info.trace import read_trace

TEAM = ("C1", "C2", "C3", "C4")


def _avg(values: list) -> float | None:
    values = [v for v in values if v is not None]
    return mean(values) if values else None


def load_runs(out: Path, benchmark: str) -> list[dict]:
    """Every result with its success flag and diagnostics."""
    runs = [json.loads(path.read_text()) for path in sorted((out / "results").glob("*.json"))]
    if benchmark == "bcp":
        cfg = load_config(ROOT / "configs/bcp.yaml")
        tasks = {task["query_id"]: task for task in load_tasks(resolve(cfg["tasks"]))}
        evidence, gold = load_qrels(resolve(cfg["qrels"]["evidence"])), load_qrels(resolve(cfg["qrels"]["gold"]))
    for run in runs:
        run["success"] = None
        if run["status"] not in ("completed", "incomplete"):
            continue
        events = read_trace(out / "traces" / f"{run['run_id']}.jsonl")
        if benchmark == "bcp":
            grade_path = out / "grades" / f"{run['run_id']}.json"
            run["success"] = json.loads(grade_path.read_text()).get("correct") if grade_path.exists() else None
            task_id = run["task_id"]
            diagnosis = bcp_diag.analyze(events, tasks[task_id], evidence.get(task_id, []), gold.get(task_id, []))
            diagnosis["category"] = bcp_diag.failure_category(diagnosis, run["success"])
        else:
            run["success"] = run.get("success")
            diagnosis = tau_diag.analyze(events, run.get("gold_actions", []))
        run["diagnosis"] = diagnosis
    return runs


def summarize(runs: list[dict], benchmark: str) -> dict:
    conditions = sorted({run["condition"] for run in runs})
    success = {c: {} for c in conditions}  # condition -> (task, repeat) -> bool
    table = {}
    for c in conditions:
        mine = [run for run in runs if run["condition"] == c]
        graded = [run for run in mine if run["success"] is not None]
        for run in graded:
            success[c][f"{run['task_id']}#{run['repeat']}"] = bool(run["success"])
        flags = [float(run["success"]) for run in graded]
        totals = [run["usage"]["total"] for run in mine if run["status"] in ("completed", "incomplete")]
        row = {
            "runs": len(mine),
            "graded": len(graded),
            "errors": sum(run["status"] == "error" for run in mine),
            "not_applicable": sum(run["status"] == "not_applicable" for run in mine),
            "success_rate": _avg(flags),
            "ci95": stats.bootstrap_ci(flags),
            "prompt_tokens": _avg([t["prompt_tokens"] for t in totals]),
            "completion_tokens": _avg([t["completion_tokens"] for t in totals]),
            "cache_hit_tokens": _avg([t["cache_hit_tokens"] for t in totals]),
            "max_context_tokens": _avg([t["max_prompt_tokens"] for t in totals]),
            "llm_calls": _avg([t["llm_calls"] for t in totals]),
            "tool_calls": _avg([sum(run["tool_call_counts"].values()) for run in mine if "diagnosis" in run]),
            "wall_seconds": _avg([run["wall_seconds"] for run in mine if "diagnosis" in run]),
        }
        diagnosed = [run["diagnosis"] for run in mine if "diagnosis" in run]
        if benchmark == "bcp":
            row.update(
                r_sys=_avg([d["evidence"]["r_sys"] for d in diagnosed]),
                r_arrive=_avg([d["evidence"]["r_arrive"] for d in diagnosed]),
                loss=_avg([d["evidence"]["loss"] for d in diagnosed]),
                answer_in_decider=_avg([float(d["answer_in_decider"]) for d in diagnosed]),
                answer_in_other=_avg([float(d["answer_in_other"]) for d in diagnosed]),
                cross_agent_repeat_search=_avg([d["searches"]["cross_agent_rate"] for d in diagnosed]),
            )
        else:
            row.update(
                delegations=_avg([d["delegations"] for d in diagnosed]),
                repeated_calls=_avg([d["repeated_calls"] for d in diagnosed]),
                down_loss_candidates=_avg([d["down_loss_candidates"] for d in diagnosed]),
            )
            trials: dict[str, list[bool]] = {}
            for run in graded:
                trials.setdefault(run["task_id"], []).append(bool(run["success"]))
            row.update(pass_1=stats.pass_hat_k(trials, 1), pass_3=stats.pass_hat_k(trials, 3))
            row["db_match"] = _avg([float(run["db_match"]) for run in graded if run.get("db_match") is not None])
        table[c] = row

    summary = {"conditions": table, "success_rate": {c: table[c]["success_rate"] for c in conditions}}
    if "C0" in success:
        summary["paired"] = {c: stats.mcnemar(success["C0"], success[c]) for c in conditions if c != "C0"}
        if benchmark == "bcp":
            by_key = {(run["condition"], f"{run['task_id']}#{run['repeat']}"): run for run in runs}
            categories = {}
            for c in conditions:
                if c == "C0":
                    continue
                specific = [k for k in success[c] if success["C0"].get(k) and not success[c][k]]
                counts: dict[str, int] = {}
                for key in specific:
                    category = by_key[(c, key)]["diagnosis"]["category"]
                    counts[category] = counts.get(category, 0) + 1
                categories[c] = {k: v / len(specific) for k, v in counts.items()} if specific else {}
            summary["mas_specific_categories"] = categories
    team = [c for c in TEAM if c in success]
    if len(team) >= 2:
        summary["oracle"] = stats.oracle(success, team)
    summary["success_rate"] = {c: r for c, r in summary["success_rate"].items() if r is not None}
    return summary


def markdown(name: str, summary: dict) -> str:
    rows = summary["conditions"]
    if not rows:
        return f"## {name}\n\nNo results.\n"
    keys = [k for k in next(iter(rows.values())) if k != "ci95"]
    lines = [f"## {name}", "", "| condition | " + " | ".join(keys) + " |", "|---" * (len(keys) + 1) + "|"]
    for c, row in rows.items():
        cells = [f"{row[k]:.3f}" if isinstance(row[k], float) else str(row[k]) for k in keys]
        lines.append(f"| {c} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("outs", nargs="+", type=Path)
    parser.add_argument("--human", type=Path, help="JSON with human-annotation results for P2-P4")
    args = parser.parse_args()
    summaries = {}
    for out in args.outs:
        benchmark = json.loads((out / "manifest.json").read_text())["frozen"]["benchmark"]
        kind = "bcp" if benchmark == "bcp" else "tau2"
        summary = summarize(load_runs(out, kind), kind)
        write_json(out / "summary.json", summary)
        (out / "summary.md").write_text(markdown(benchmark, summary), encoding="utf-8")
        print(markdown(benchmark, summary))
        summaries[benchmark] = summary
    human = json.loads(args.human.read_text()) if args.human else None
    verdict = criteria.evaluate(summaries, human)
    write_json(args.outs[0] / "criteria.json", verdict)
    print(json.dumps({p: v["status"] for p, v in verdict.items() if p != "thresholds"}, indent=2))


if __name__ == "__main__":
    main()
