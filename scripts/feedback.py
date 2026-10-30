#!/usr/bin/env python3
"""Build information-level review packets without any judge/model call."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analysis.information import decision_case
from analysis.runs import load_runs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--report-dir", required=True, type=Path)
    parser.add_argument("--agent")
    parser.add_argument("--call-t", type=int)
    args = parser.parse_args()
    if args.report_dir.resolve().is_relative_to(args.output.resolve()):
        parser.error("Review packets must be separate from the immutable experiment")
    args.report_dir.mkdir(parents=True, exist_ok=False)
    runs, traces = load_runs(args.output)
    rows = []
    for run_index, result in enumerate(runs):
        events = traces[result['run_id']]
        members = next((e['control']['team']['members'] for e in events if e['type'] == 'team_spec'), [])
        workers = {m['role'] for m in members if m['template'] != 'leader'}
        decisions = [e for e in events if e['type'] == 'model_input' and e['agent'] in workers
                     and (args.agent is None or e['agent'] == args.agent)
                     and (args.call_t is None or e['t'] == args.call_t)]
        if not decisions:
            rows.append(dict(run_id=result['run_id'], review_status='no_worker_decision', run_status=result['status']))
        for call in decisions:
            case = decision_case(events, call['agent'], call['t'])
            case.update(run_id=result['run_id'], run_status=result['status'], decision_kind='worker_step',
                        task_grade=result['grade'], failure_class=result.get('failure_class'))
            name = f"{run_index}-{call['agent']}-{call['t']}.json"
            (args.report_dir / name).write_text(json.dumps(case, ensure_ascii=False, indent=2))
            rows.append(dict(run_id=result['run_id'], agent=call['agent'], request_id=call['t'],
                             packet=name, semantic_attribution='unknown', causal_attribution='not_tested'))
    (args.report_dir / "index.json").write_text(json.dumps(rows, indent=2))
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
