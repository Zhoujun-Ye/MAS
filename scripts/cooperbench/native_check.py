#!/usr/bin/env python3
"""Verify selected base/gold tasks in isolated local Docker, without any model."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import hashlib
import fcntl
import re
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from benchmarks.cooperbench.adapter import Pair, verify_checkout, REVISION
from benchmarks.cooperbench.native import load_evaluator, BACKEND_VERSION
from benchmarks.cooperbench.isolation import prepare_worker, ISOLATION_VERSION
from harness.execution import ContainerWorkspace
from benchmarks.cooperbench.selection import load_selection, all_task_pairs
from benchmarks.cooperbench.environment import resolve


def validation_fingerprint():
    paths = [Path(__file__), ROOT / 'harness/execution.py', ROOT / 'harness/agent.py']
    paths += [ROOT / 'benchmarks/cooperbench' / name for name in
              ('native.py', 'environment.py', 'offline_assets.py', 'adapter.py', 'isolation.py', 'snapshot.py')]
    return hashlib.sha256(b''.join(str(p.relative_to(ROOT)).encode() + p.read_bytes()
                                  for p in sorted(paths))).hexdigest()


def cache_key(pair, environment, fingerprint):
    return hashlib.sha256(json.dumps(dict(pair=pair.key, environment=environment,
        fingerprint=fingerprint, revision=REVISION, backend=BACKEND_VERSION), sort_keys=True).encode()).hexdigest()


def baseline_failure_evidence(result):
    """Recognize an actual test assertion, not an arbitrary nonzero process."""
    if result.get('error') or result.get('passed') is True:
        return None
    if result.get('tests_failed', 0) > 0:
        return dict(kind='parsed-test-failure')
    output = re.sub(r'\x1b\[[0-9;]*m', '', result.get('output', result.get('test_output', '')))
    # Jest can terminate on an unhandled asynchronous expectation before its
    # summary reporter runs. Preserve raw counts and require a test-source frame.
    assertion = re.search(r'^JestAssertionError: expect\([^\n]+', output, re.M)
    source = re.search(r'^\s+at expect \((/workspace/repo/[^\n]*?(?:__tests__/|\.test\.)[^\n]*?:\d+:\d+)\)', output, re.M)
    if (result.get('exit_code') == 1 and assertion and source
            and 'Received promise rejected instead of resolved' in output):
        return dict(kind='unhandled-jest-expectation', assertion=assertion.group(0), test_source=source.group(1))
    return None


def reusable(row, pair, environment, fingerprint):
    return (row.get('pair') == pair.key and row.get('validation_fingerprint') == fingerprint
            and row.get('gate_passed') is True
            and all(row.get(k) == v for k, v in environment.items())
            and len(row.get('features', [])) == 2
            and [r.get('feature') for r in row['features']] == list(pair.features)
            and all(r.get('gate_passed') is True and baseline_failure_evidence(r['baseline'])
                    and r['gold'].get('passed') is True and not r['gold'].get('error') for r in row['features'])
            and row.get('gold_joint', {}).get('both_passed') is True
            and not row.get('gold_joint', {}).get('error'))


def check(pair, dataset, module):
    environment = resolve(pair.image)
    task = dataset / pair.repo / f'task{pair.task_id}'
    worker = module.get_backend('docker').create_sandbox(pair.image, timeout=1800, workdir='/workspace/repo')
    try:
        isolation = prepare_worker(ContainerWorkspace(worker.container, '/workspace/repo', timeout=180))
    finally:
        worker.terminate()
    rows = []
    for feature in pair.features:
        sb = module.get_backend('docker').create_sandbox(pair.image, timeout=1800)
        try:
            base = sb.exec('git', '-C', '/workspace/repo', 'rev-parse', 'HEAD').stdout_read().strip()
            module._write_patch(sb, 'tests.patch', (task / f'feature{feature}/tests.patch').read_text())
            # The shared Docker backend retains Go runner failure diagnostics.
            baseline = module._run_tests(sb, 'tests.patch', '', base)
        finally:
            sb.terminate()
        gold = module.run_patch_test(pair.repo, pair.task_id, feature,
                                    agent_patch=task / f'feature{feature}/feature.patch', dataset_dir=dataset, timeout=1800)
        failure_evidence = baseline_failure_evidence(baseline)
        passed = bool(failure_evidence and gold['passed'] and not gold.get('error'))
        rows.append(dict(feature=feature, baseline=baseline, baseline_failure_evidence=failure_evidence,
                         gold=gold, gate_passed=passed))
    combined = task / 'combined.patch'
    joint = (module.test_merged(pair.repo, pair.task_id, *pair.features, patch1=combined, patch2=combined,
                               dataset_dir=dataset, timeout=1800) if combined.exists() else
             module.test_merged(pair.repo, pair.task_id, *pair.features,
                                patch1=task / f'feature{pair.features[0]}/feature.patch',
                                patch2=task / f'feature{pair.features[1]}/feature.patch', dataset_dir=dataset, timeout=1800))
    return dict(pair=pair.key, **environment, worker_isolation=isolation, features=rows, gold_joint=joint,
                gate_passed=all(r['gate_passed'] for r in rows) and joint.get('both_passed') is True and not joint.get('error'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--authorized-local-evaluation', action='store_true', required=True)
    parser.add_argument('--jobs', type=int, choices=(1, 2, 4), default=1,
                        help='Independent offline cases only; paid task concurrency remains one')
    parser.add_argument('--selection', type=Path)
    parser.add_argument('--all-tasks', action='store_true')
    args = parser.parse_args()
    if not args.selection and not args.all_tasks:
        parser.error('Specify --all-tasks, --selection, or both for a deduplicated queue')
    cache = ROOT / '.cache/cooperbench-validation'
    cache.mkdir(parents=True, exist_ok=True)
    lock = (cache / 'queue.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    args.output.mkdir(parents=True, exist_ok=False)
    dataset = verify_checkout()
    all_pairs = all_task_pairs(dataset) if args.all_tasks else []
    selected = load_selection(args.selection) if args.selection else []
    pairs = list({p.key: p for p in all_pairs + selected}.values())
    fingerprint = validation_fingerprint()
    (args.output / 'queue-manifest.json').write_text(json.dumps(dict(
        validation_fingerprint=fingerprint, pairs=[p.key for p in pairs], jobs=args.jobs, paid_calls=0), indent=2))
    module = load_evaluator()
    def evaluate(item):
        index, pair = item
        reused = False
        try:
            if validation_fingerprint() != fingerprint:
                raise RuntimeError('Validation code changed; refuse mixed-code evidence')
            environment = resolve(pair.image)
            directory = cache / cache_key(pair, environment, fingerprint)
            directory.mkdir(exist_ok=True)
            result = None
            for previous in sorted(directory.glob('*.json')):
                candidate = json.loads(previous.read_text())
                if reusable(candidate, pair, environment, fingerprint):
                    result = dict(candidate, reused_from=str(previous),
                                  reused_sha256=hashlib.sha256(previous.read_bytes()).hexdigest())
                    reused = True
                    break
            if result is None:
                result = check(pair, dataset, module)
                if validation_fingerprint() != fingerprint or resolve(pair.image) != environment:
                    raise RuntimeError('Code or environment changed during validation; result not admissible')
                result['validation_fingerprint'] = fingerprint
                path = directory / (uuid.uuid4().hex + '.json')
                temporary = path.with_suffix('.tmp')
                temporary.write_text(json.dumps(result, indent=2))
                temporary.rename(path)
        except Exception as error:
            result = dict(pair=pair.key, gate_passed=False, error_type=type(error).__name__, error=str(error))
        (args.output / f'{index}.json').write_text(json.dumps(result, indent=2))
        row = dict(pair=pair.key, gate_passed=result['gate_passed'], reused=reused)
        print(json.dumps(row), flush=True)
        return result
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        records = list(pool.map(evaluate, enumerate(pairs)))
    results = [dict(pair=r['pair'], gate_passed=r['gate_passed']) for r in records]
    summary = dict(revision=REVISION, backend=BACKEND_VERSION, validation_fingerprint=fingerprint,
                   worker_isolation=ISOLATION_VERSION, results=results,
                   paid_calls=0, all_passed=all(r['gate_passed'] for r in results))
    (args.output / 'summary.json').write_text(json.dumps(summary, indent=2))
    if args.all_tasks and args.selection:
        by_pair = {r['pair']: r for r in records}
        for name, group in [('all', all_pairs), ('selected', selected)]:
            folder = args.output / name
            folder.mkdir()
            rows = []
            for index, pair in enumerate(group):
                result = by_pair[pair.key]
                (folder / f'{index}.json').write_text(json.dumps(result, indent=2))
                rows.append(dict(pair=pair.key, gate_passed=result['gate_passed']))
            (folder / 'summary.json').write_text(json.dumps(dict(summary, results=rows,
                all_passed=all(r['gate_passed'] for r in rows)), indent=2))
    if not summary['all_passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
