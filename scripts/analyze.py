"""Read existing results/traces without benchmark code or model calls.

Never regrade answers or infer semantic loss. Reports go to a fresh directory.
Historical P1-P4 thresholds are preserved in analysis/criteria.py, but are not
automatically applied to a new team experiment.
"""
import argparse
import json
from pathlib import Path
from statistics import mean
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analysis import cache, stats
from harness.runner import write_json
from harness.trace import read_trace, tool_counts, usage_summary, validate


def load_runs(out):
    runs, traces = [], {}
    for path in sorted((out / "results").glob("*.json")):
        run = json.loads(path.read_text())
        trace_path = out / "traces" / f"{run['run_id']}.jsonl"
        events = read_trace(trace_path) if trace_path.exists() else []
        traces[run["run_id"]] = events
        grade_path = out / "grades" / f"{run['run_id']}.json"
        value = json.loads(grade_path.read_text()).get("correct") if grade_path.exists() else run.get("success")
        run["success"] = value if (run["status"] == "completed" and isinstance(value, bool)
                                   and any(e["type"] == "final" for e in events)) else None
        run["usage"] = usage_summary(events) if events else run.get("usage", usage_summary([]))
        run["tool_counts"] = tool_counts(events)
        runs.append(run)
    return runs, traces


def summarize(runs):
    table = {}
    for condition in sorted({r["condition"] for r in runs}):
        rows = [r for r in runs if r["condition"] == condition]
        graded = [r["success"] for r in rows if r["success"] is not None]
        totals = [r["usage"]["total"] for r in rows]
        completed = sum(r["status"] == "completed" for r in rows)
        prompt = sum(t["prompt_tokens"] for t in totals)
        estimates = [r.get("cost_usd_estimate") for r in rows]
        table[condition] = dict(
            runs=len(rows), graded=len(graded), ungraded=len(rows) - len(graded),
            completed=completed,
            grading_coverage=len(graded) / completed if completed else None,
            success_rate_scope="success_rate/ci95 require all completed runs graded; graded_success_rate excludes unknowns.",
            confirmed_successes=sum(value is True for value in graded),
            confirmed_success_fraction=sum(value is True for value in graded) / completed if completed else None,
            errors=sum(r["status"] == "error" for r in rows),
            incomplete=sum(r["status"] == "incomplete" for r in rows),
            success_rate=mean(graded) if graded and len(graded) == completed else None,
            graded_success_rate=mean(graded) if graded else None,
            ci95=stats.bootstrap_ci([float(x) for x in graded]) if graded and len(graded) == completed else None,
            prompt_tokens=prompt, completion_tokens=sum(t["completion_tokens"] for t in totals),
            cache_hit_rate=sum(t["cache_hit_tokens"] for t in totals) / prompt if prompt else None,
            llm_calls=sum(t["llm_calls"] for t in totals),
            estimated_cost_usd=sum(estimates) if all(x is not None for x in estimates) else None,
            budget_exhausted_runs=sum(r["tool_counts"].get("refused_over_budget", 0) > 0 for r in rows),
            semantic_loss=None,
        )
    return dict(conditions=table, accounting_scope="Latest result files only; planning, judges and retry attempts may add cost.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("outs", type=Path, nargs="+")
    parser.add_argument("--report-dir", type=Path, required=True)
    args = parser.parse_args()
    if any(args.report_dir.resolve().is_relative_to(p.resolve()) for p in args.outs):
        parser.error("Reports must be outside source output directories")
    args.report_dir.mkdir(parents=True, exist_ok=False)
    for index, out in enumerate(args.outs):
        runs, traces = load_runs(out)
        report = summarize(runs)
        report["cache"] = cache.summarize([(r["condition"], traces[r["run_id"]]) for r in runs])
        report["log_problems"] = {key: issues for key, events in traces.items() if (issues := validate(events))}
        report["retry_attempt_traces"] = len(list((out / "traces/attempts").glob("*.jsonl")))
        write_json(args.report_dir / f"{index}-{out.name}.json", report)
        print(json.dumps({"source": str(out), **report}, ensure_ascii=False))


if __name__ == "__main__":
    main()
