"""Offline answer scoring into a fresh namespace, never rewriting original evidence."""
import argparse
from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from benchmarks.kramabench.evaluation import NUMERIC_POLICIES, NUMERIC_POLICY, grade_answer, scoring_contract
from common.io import write_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', type=Path, required=True)
    parser.add_argument('--runs', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--numeric-policy', choices=NUMERIC_POLICIES, default=NUMERIC_POLICY)
    args = parser.parse_args(argv)
    contract = scoring_contract(args.upstream, numeric_policy=args.numeric_policy)
    if args.output.resolve().is_relative_to(args.runs.resolve()):
        parser.error('Output must be outside original run evidence')
    args.output.mkdir(parents=True, exist_ok=False)
    statuses, rows = Counter(), []
    for report in sorted(args.runs.glob('*/*/report.json')):
        task_id, arm = report.parent.parent.name, report.parent.name
        submission = report.parent / 'submission.json'
        grade = grade_answer(args.upstream, task_id, submission if submission.exists() else None,
                             numeric_policy=args.numeric_policy)
        write_json(args.output / task_id / arm / 'grade.json', grade)
        statuses[grade['status']] += 1
        rows.append(dict(task_id=task_id, arm=arm, status=grade['status'], metric=grade['metric'],
                         score=grade['score'], score_kind=grade['score_kind']))
    result = dict(scoring=contract, attempts=len(rows), statuses=dict(statuses), rows=rows,
                  judge_calls=0, original_evidence_modified=False)
    write_json(args.output / 'summary.json', result)
    return result


if __name__ == '__main__':
    main()
