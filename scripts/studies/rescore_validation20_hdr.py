"""Two explicitly authorized HDR regrades from immutable existing artifacts."""
import argparse
import copy
import hashlib
import json
from pathlib import Path

from analysis.native_evidence import native_subagents
from benchmarks._external import digest, write_jsonl
from benchmarks._io import write_json
from scripts.common import runtime, score
from scripts.studies.matched_matrix_report import collect, lines, price, summarize, write_report

IDS = ('sql2s_103', 'parallel_009')
BACKEND = 'claude-code-subagents'


def recover(out):
    plan = json.loads((out / 'plan.json').read_text())
    task, = plan['task_ids']
    folder = out / task / BACKEND
    report = json.loads((folder / 'report.json').read_text())
    cli = report['cli']
    if cli['status'] != 'cli_exited' or cli['returncode'] != 0:
        raise ValueError('Only successfully exited original CLI artifacts are eligible')
    audit = native_subagents(folder)
    if not audit['passed']:
        raise ValueError('Revised lifecycle audit failed')
    submission = folder / 'submission.json'
    if submission.exists():
        if submission.is_symlink() or digest(submission) != report.get('submission_sha256'):
            raise ValueError('Original submission hash mismatch')
        answer = json.loads(submission.read_text())['final_answer']
        origin = 'original_hash_bound_submission'
    else:
        if task != 'sql2s_103' or report.get('submission_sha256'):
            raise ValueError('Unexpected missing submission')
        answer = cli['native_result']['result']
        origin = 'recovered_cli_final_missing_submission'
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError('No existing answer to grade')
    return plan, report, answer, dict(task_id=task, origin=origin,
        source_report_sha256=digest(folder / 'report.json'),
        source_predictions_sha256=digest(out / 'predictions.jsonl'),
        source_plan_sha256=digest(out / 'plan.json'),
        answer_sha256=hashlib.sha256(answer.encode()).hexdigest(), audit=audit)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--credentials', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--authorized-judges', type=int, default=0)
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    if output == source or output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError('Derived evidence must be separate')
    recovered = [(t, recover(source / 'solvers/hybriddeepresearch' / t / BACKEND)) for t in IDS]
    if not args.execute:
        print(json.dumps(dict(solver_calls=0, judge_calls=2,
            recoveries=[r[3] for _, r in recovered])))
        return
    if args.authorized_judges != 2:
        raise ValueError('Require exact authorization for two judge calls, no retries')
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    original = collect(source)
    updated = copy.deepcopy(original)
    key = runtime.credential(args.credentials)
    before = runtime.safe_balance(key, output, 'balance-before')
    changes = []
    for task, (plan, report, answer, provenance) in recovered:
        run = output / 'recovered' / task
        folder = run / task / BACKEND
        folder.mkdir(parents=True)
        write_json(run / 'plan.json', plan)
        write_json(folder / 'submission.json', dict(final_answer=answer))
        prediction = dict(report, final_answer=answer, status='native_condition_unverified',
                          submission_sha256=digest(folder / 'submission.json'))
        write_jsonl(run / 'predictions.jsonl', [prediction])
        write_json(run / 'recovery-provenance.json', provenance)
        grade = output / 'grades' / task
        code = score.main(['--run', str(run), '--upstream', str(args.root / 'hybriddeepresearch/upstream'),
            '--tasks', str(args.root / 'hybriddeepresearch/release/hybrid_ds_release/hybrid_ds_release.jsonl'),
            '--output', str(grade), '--execute-judges', '--judge-limit', '1',
            '--judge-model', 'deepseek-flash', '--credentials', str(args.credentials),
            '--judge-base-url', 'https://api.deepseek.com'], benchmark='hybriddeepresearch')
        judged, = lines(grade / 'judge-results.jsonl')
        row = next(r for r in updated['rows'] if r['task_id'] == task and r['backend'] == BACKEND
                   and r['benchmark'] == 'hybriddeepresearch')
        previous = copy.deepcopy(row)
        row.update(score=judged.get('score'), grade_status=judged['status'],
                   native_audit_passed=True, recovery_origin=provenance['origin'],
                   original_status=row['status'],
                   status='cli_exited' if provenance['origin'] == 'original_hash_bound_submission'
                   else provenance['origin'])
        row['judge_usd_offpeak'] = price((judged.get('raw_response') or {}).get('usage'))
        costs = [row['model_usd_offpeak'], row['web_usd_estimate'], row['judge_usd_offpeak']]
        row['total_usd_offpeak'] = sum(costs) if all(c is not None for c in costs) else None
        changes.append(dict(task_id=task, previous=previous, revised=copy.deepcopy(row),
                            provenance=provenance, grading_exit_code=code, grade_evidence=str(grade)))
        if code:
            break
    after = runtime.safe_balance(key, output, 'balance-after')
    updated['run'] += '-regraded-hdr-01'
    updated['groups'] = summarize(updated['rows'])
    updated['regrading'] = dict(source=str(source), source_summary_sha256=digest(source / 'summary.json'),
        solver_calls=0, authorized_judges=2, retries=0, changes=changes,
        account_delta=runtime.balance_deltas(before, after) if before and after else None)
    updated['limitations'].append('sql2s_103 uses saved CLI final text: missing required original submission; '
        'its recovered score is not an original-protocol compliant result. Other rows are unchanged, '
        'including the previously reported Krama lifecycle exception.')
    write_report(updated, output / 'report')
    path = output / 'report/REPORT.md'
    with path.open('a') as stream:
        stream.write('\n## Regrading Provenance\n\nNo solver rerun or prompt change. Two judge calls maximum, no retries.\n')
        for item in changes:
            stream.write(f"- {item['task_id']}: {item['provenance']['origin']}; score {item['revised']['score']}.\n")
    write_json(output / 'regrading-receipt.json', updated['regrading'])
    print(json.dumps(dict(groups=updated['groups'], regrading_account_delta=updated['regrading']['account_delta'])))


if __name__ == '__main__':
    main()
