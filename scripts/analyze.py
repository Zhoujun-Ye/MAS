"""Read per-attempt output directories without benchmark code or model calls.

Never regrade answers or infer semantic loss. Reports go to a fresh directory.
Historical P1-P4 thresholds are preserved in analysis/criteria.py, but are not
automatically applied to a new team experiment.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analysis import cache, stats
from harness.runner import write_json
from harness.trace import validate


from analysis.runs import load_runs


def summarize(runs):
    table = {}
    for condition in sorted({r["condition"] for r in runs}):
        rows = [r for r in runs if r["condition"] == condition]
        totals = [r["usage"]["total"] for r in rows]
        known = [r["success"] for r in rows if isinstance(r["success"], bool)]
        successes = sum(v is True for v in known)
        prompt = sum(t["prompt_tokens"] for t in totals)
        estimates = [r.get("cost_usd_estimate") for r in rows]
        table[condition] = dict(
            runs=len(rows), denominator="all_started_runs", graded=len(known), ungraded=len(rows)-len(known),
            confirmed_successes=successes, success_rate=successes / len(rows),
            success_rate_scope="Confirmed successes / all started runs; unresolved and infrastructure outcomes remain in denominator.",
            success_rate_upper_bound=(successes + len(rows) - len(known)) / len(rows),
            agent_failures=sum(r.get("failure_class") == "agent_failure" for r in rows),
            infrastructure_errors=sum(r.get("failure_class") == "infrastructure_error" for r in rows),
            external_interruptions=sum(r.get("failure_class") == "external_interruption" for r in rows),
            evaluator_errors=sum(r.get("evaluator_error", False) for r in rows),
            incomplete=sum(r["status"] == "incomplete" for r in rows),
            ci95=stats.bootstrap_ci([float(x) for x in known]) if len(known) == len(rows) else None,
            prompt_tokens=prompt, completion_tokens=sum(t["completion_tokens"] for t in totals),
            cache_hit_rate=sum(t["cache_hit_tokens"] for t in totals) / prompt if prompt else None,
            llm_calls=sum(t["llm_calls"] for t in totals),
            estimated_cost_usd=sum(estimates) if all(x is not None for x in estimates) else None,
            account_balance_deltas=[r.get("account_balance_delta") for r in rows],
            semantic_loss=None)
        table[condition]['research_audit_counts'] = {status: sum(r.get('research_audit', {}).get('status', 'not_audited') == status
            for r in rows) for status in ('not_audited', 'admissible', 'contaminated', 'uncontrolled_environment')}
        table[condition]['research_admissible_successes'] = sum(r['success'] is True and
            r.get('research_audit', {}).get('status') == 'admissible' for r in rows)
        table[condition]['research_scope'] = 'Task success is not research admissibility. Contaminated/unreviewed runs remain in totals; do not interpret the raw rate as clean benchmark performance.'
    return dict(conditions=table, accounting_scope="All started attempt directories, including failures. Account deltas may overlap and are not summed.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("outs", type=Path, nargs="+")
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument('--audit-file', type=Path, help='External immutable-trace SHA-256 keyed research audit JSON')
    args = parser.parse_args()
    if any(args.report_dir.resolve().is_relative_to(p.resolve()) for p in args.outs):
        parser.error("Reports must be outside source output directories")
    args.report_dir.mkdir(parents=True, exist_ok=False)
    for index, out in enumerate(args.outs):
        audits = json.loads(args.audit_file.read_text())['trace_audits'] if args.audit_file else None
        runs, traces = load_runs(out, audits)
        report = summarize(runs)
        report["cache"] = cache.summarize([(r["condition"], traces[r["run_id"]]) for r in runs])
        report["log_problems"] = {key: issues for key, events in traces.items() if (issues := validate(events))}
        report["started_attempt_directories"] = len(runs)
        write_json(args.report_dir / f"{index}-{out.name}.json", report)
        print(json.dumps({"source": str(out), **report}, ensure_ascii=False))


if __name__ == "__main__":
    main()
