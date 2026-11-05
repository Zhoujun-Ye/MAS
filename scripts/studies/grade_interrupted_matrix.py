"""Grade retained matrix attempts after a transport failure; never launch solvers."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

from benchmarks._io import write_json
from benchmarks.kramabench.tasks import load_tasks
from scripts.common import runtime
from scripts.common.grading import grade_attempt


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

    def command_run(command, log):
        env = {name: os.environ[name] for name in ('PATH', 'HOME', 'LANG') if name in os.environ}
        with Path(str(log) + '.stdout.log').open('x') as stdout, \
                Path(str(log) + '.stderr.log').open('x') as stderr:
            return subprocess.run(command, stdout=stdout, stderr=stderr, env=env, timeout=3900).returncode

    def score(row):
        b, t, k = row['benchmark'], row['task_id'], row['backend']
        out = Path(row['run'])
        artifact = out / ('summary.json' if b == 'kramabench' else 'predictions.jsonl')
        if not artifact.is_file():
            raise FileNotFoundError(artifact)
        # Recovery retains the original public HDR ID-prefix category rule.
        task = SimpleNamespace(id=t, category='search_to_sql' if t.startswith('s2sql_') else None,
                               query=queries[t] if b == 'kramabench' else None)
        return grade_attempt(b, task, k, out, data_root=args.root, grades_root=root / 'grades',
            credentials=args.credentials, judge_enabled=True, key=key, command_run=command_run,
            log=recovery / (b + '-' + t + '-' + k))

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
