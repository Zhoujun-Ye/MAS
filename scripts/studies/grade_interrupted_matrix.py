"""Grade retained matrix attempts after a transport failure; never launch solvers."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import subprocess
import sys

from benchmarks._io import write_json
from benchmarks.kramabench.tasks import load_tasks
from benchmarks.kramabench.semantic_judge import judge_once
from scripts.common import runtime


def retained_rows(root, authorization):
    rows = []
    for item in authorization['selections']:
        b, t, k = item['benchmark'], item['task_id'], item['backend']
        out = root / 'solvers' / b / t / k
        report = out / t / k / 'report.json'
        if not report.is_file():
            raise ValueError('Missing retained attempt; recovery does not launch solvers')
        record = json.loads(report.read_text())
        if record['status'] in {'running', 'not_started'}:
            raise ValueError('Attempt is not terminal; inspect live processes first')
        rows.append(dict(item, status=record['status'], run=str(out),
                         returncode=record.get('cli', {}).get('returncode')))
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--credentials', type=Path, default=Path('/home/zhoujunye/MAS-information/.env'))
    parser.add_argument('--authorized-judges', type=int)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args(argv)
    root = args.run.resolve()
    authorization = json.loads((root / 'authorization.json').read_text())
    rows = retained_rows(root, authorization)
    maximum = authorization['maximum_judge_calls']
    if not args.execute:
        print(json.dumps(dict(retained_attempts=len(rows), new_solver_calls=0, maximum_judge_calls=maximum)))
        return 0
    if args.authorized_judges != maximum or authorization.get('authorized_judges') != maximum:
        raise ValueError('Require the original explicit judge authorization')
    if (root / 'summary.json').exists() or (root / 'grades').exists():
        raise ValueError('Refuse to overwrite results or repeat grading')
    os.umask(0o077)
    recovery = root / 'grading-recovery'
    recovery.mkdir(exist_ok=False)
    write_json(recovery / 'authorization.json', dict(new_solver_calls=0, maximum_judge_calls=maximum,
        judge_concurrency=2, retries=0, recovered_attempts=len(rows)))
    key = runtime.credential(args.credentials)
    before = runtime.safe_balance(key, recovery, 'balance-before')
    tasks, _ = load_tasks(args.root / 'kramabench/upstream')
    queries = {t.id: t.query for t in tasks}

    def score(row):
        b, t, k = row['benchmark'], row['task_id'], row['backend']
        out = Path(row['run'])
        target = root / 'grades' / b / t / k
        result = dict(benchmark=b, task_id=t, backend=k, judge_calls=0)
        if b == 'kramabench':
            record = json.loads((out / 'summary.json').read_text())['rows'][0]
            result.update(status=record.get('grade', {}).get('status'), grade=record.get('grade'),
                pipeline_exit_code=record.get('pipeline_exit_code'),
                pipeline_answer_matches_submission=record.get('pipeline_answer_matches_submission'))
            if record.get('status') == 'cli_exited' and result['status'] == 'pending_judge':
                judged = judge_once(upstream=args.root / b / 'upstream', task_id=t, backend=k,
                    submission_path=out / t / k / 'submission.json', question=queries[t], key=key, output=target)
                result.update(status=judged['status'], grade=judged.get('grade'), judge_calls=judged['attempted_calls'])
            return result
        predictions = [json.loads(line) for line in (out / 'predictions.jsonl').read_text().splitlines() if line.strip()]
        # The frozen ID prefix encodes the public HDR category, not its gold.
        text_judge = b == 'dataclawbench' or not t.startswith('s2sql_')
        calls = sum(bool(p['final_answer'].strip()) for p in predictions) if text_judge else 0
        command = [sys.executable, '-m', 'scripts.' + b + '.score', '--run', str(out),
            '--upstream', str(args.root / b / 'upstream'), '--output', str(target)]
        if b == 'hybriddeepresearch':
            command += ['--tasks', str(args.root / 'hybriddeepresearch/release/hybrid_ds_release/hybrid_ds_release.jsonl'),
                        '--db-root', str(args.root / 'hybriddeepresearch/data')]
            if not text_judge:
                command.append('--execute-sql')
        if calls:
            command += ['--execute-judges', '--judge-limit', str(calls), '--judge-model', 'deepseek-flash',
                        '--credentials', str(args.credentials), '--judge-base-url', 'https://api.deepseek.com']
        env = {name: os.environ[name] for name in ('PATH', 'HOME', 'LANG') if name in os.environ}
        with (recovery / (b + '-' + t + '-' + k + '.stdout.log')).open('x') as stdout, \
                (recovery / (b + '-' + t + '-' + k + '.stderr.log')).open('x') as stderr:
            code = subprocess.run(command, stdout=stdout, stderr=stderr, env=env, timeout=3900).returncode
        receipt = json.loads((target / 'receipt.json').read_text()) if (target / 'receipt.json').exists() else {}
        return {**result, 'status': 'completed' if code == 0 else 'grading_failed', 'returncode': code,
                'judge_calls': receipt.get('judge_calls'), 'output': str(target)}

    grades = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        for future in as_completed([pool.submit(score, row) for row in rows]):
            grades.append(future.result())
            write_json(root / 'grading-progress.json', dict(rows=grades))
    after = runtime.safe_balance(key, recovery, 'balance-after')
    original_before = json.loads((root / 'balance-before.json').read_text())
    write_json(root / 'summary.json', dict(rows=rows, grades=grades, authorization=authorization,
        account_delta=runtime.balance_deltas(original_before, after) if after else None,
        grading_account_delta=runtime.balance_deltas(before, after) if before and after else None,
        accounting_scope='Whole shared-account interval, not attributable per-condition charges',
        original_transport_failure_preserved=True, recovered_without_solver_retries=True,
        finished_at=runtime.now()))
    print(json.dumps(dict(retained_attempts=len(rows), graded_attempts=len(grades),
                          judge_calls=sum(g.get('judge_calls') or 0 for g in grades), new_solver_calls=0)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
