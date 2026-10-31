#!/usr/bin/env python3
"""Run the frozen twenty-pair selection once, only after every gate passes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import shutil
import threading
import fcntl
import time
from dataclasses import asdict, replace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from benchmarks.cooperbench.adapter import REVISION, verify_checkout, Pair, LIMITS, MEMBER_LIMITS, load_submitted_patches
from benchmarks.cooperbench.native import DockerBackend, BACKEND_VERSION, BUILD_WHEELS
from benchmarks.cooperbench.selection import load_selection, all_task_pairs, lite, validate_expansion
from benchmarks.cooperbench.isolation import prepare_worker, ISOLATION_VERSION
from benchmarks.cooperbench.environment import resolve
from harness.config import source_digest, load_config, load_env, canonical
from harness.execution import ContainerWorkspace
from harness.runner import bounded_jobs, write_json
from harness.llm import ModelConfig
from harness.accounting import observed_balance, report as cost_report
from harness.trace import read_trace
from scripts.cooperbench.native_check import validation_fingerprint
from benchmarks.cooperbench.diagnostics import benchmark_issues


def validate_lite_selection(selection, dataset, reused_runs=()):
    # JSON round trips convert feature tuples to lists; compare serialized values.
    if canonical(selection) != canonical(lite(dataset)) or reused_runs:
        raise ValueError('Lite requires the complete official selection and fresh attempts')


def repair_sources(folders, pairs):
    """Bind explicitly authorized errata reruns to failed, immutable originals."""
    if len(folders) != len(pairs):
        raise ValueError('One original failed run required for each repair pair')
    receipts = {}
    for folder, pair in zip(folders, pairs):
        manifest = json.loads((folder / 'manifest.json').read_text())
        result = json.loads((folder / 'result.json').read_text())
        grade = json.loads((folder / 'grade.json').read_text())
        if canonical(manifest['pair']) != canonical(asdict(pair)) or grade.get('correct') is not False:
            raise ValueError('Repair source must be the same failed pair')
        issues = benchmark_issues(pair)
        if not issues:
            raise ValueError('Paid repair requires a registered benchmark erratum')
        load_submitted_patches(folder, manifest, result)
        receipts[pair.key] = dict(original=str(folder.resolve()), issues=issues,
            evidence_sha256={name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
                            for name in ('manifest.json', 'result.json', 'grade.json', 'trace.jsonl')})
    return receipts


def validate_gates(folder, pairs):
    summary = json.loads((folder / 'summary.json').read_text())
    if (summary['revision'] != REVISION or summary['backend'] != BACKEND_VERSION
            or summary.get('validation_fingerprint') != validation_fingerprint()
            or summary.get('worker_isolation') != ISOLATION_VERSION or not summary['all_passed']
            or len(summary['results']) != len(pairs)):
        raise ValueError('Native gates incomplete or incompatible; no paid calls allowed')
    for index, pair in enumerate(pairs):
        gate = json.loads((folder / f'{index}.json').read_text())
        if (gate['pair'] != pair.key or not gate['gate_passed']
                or gate.get('validation_fingerprint') != summary['validation_fingerprint']):
            raise ValueError('Gate does not match frozen selection')
        environment = resolve(pair.image)
        if any(environment[key] != gate[key] for key in environment):
            raise ValueError('Image changed since gate')


def capacity_failure(result, events):
    return bool(result.get('halted_members') or result.get('snapshot_errors')
                or result.get('reason') == 'time_limit'
                or result.get('termination') in ('time_limit', 'budget_finalization', 'message_limit_finalization')
                or any(e['type'] in ('output_recovery', 'member_budget_denial')
                       or e.get('budget_exhausted') or e.get('truncated') for e in events))


def gate_digests(*folders):
    return {str(folder): {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in folder.glob('*.json')} for folder in folders}


def cleanup_worker(sandbox):
    """Retry only disposal, never a model call; retain every failed attempt."""
    errors = []
    for attempt in range(3):
        try:
            sandbox.terminate()
            return dict(container=sandbox.container, removed=True, errors=errors)
        except Exception as error:
            stderr = getattr(error, 'stderr', None)
            if isinstance(stderr, bytes):
                stderr = stderr.decode('utf-8', errors='replace')
            errors.append(dict(error_type=type(error).__name__, message=str(error), stderr=stderr))
            if attempt < 2:
                time.sleep(1)
    return dict(container=sandbox.container, removed=False, errors=errors)


def prior_attempts(folders, pairs, selection):
    """Continue only never-started pairs, without importing or filtering scores."""
    skipped, receipts = set(), {}
    resolved = {str(Path(p).resolve()) for p in folders}
    if len(resolved) != len(folders):
        raise ValueError('Duplicate predecessor batch')
    for folder in map(Path, folders):
        manifest = json.loads((folder / 'pilot-manifest.json').read_text())
        if canonical(manifest['selection']) != canonical(selection):
            raise ValueError('Predecessor selection differs')
        if not set(manifest.get('continued_batches', {})) <= resolved:
            raise ValueError('Include the complete predecessor chain')
        rows = json.loads((folder / 'pilot-summary.json').read_text())
        if not (folder / 'batch-accounting.json').exists():
            raise ValueError('Predecessor has not finished accounting')
        started = {r['index'] for r in rows if r.get('paid_attempts', 0) > 0}
        started.update(int(p.parent.name) for p in folder.glob('*/manifest.json'))
        for row in rows:
            i = row['index']
            if not 0 <= i < len(pairs) or row['pair'] != pairs[i].key:
                raise ValueError('Predecessor pair/index mismatch')
        if any(not 0 <= i < len(pairs) for i in started) or skipped & started:
            raise ValueError('Invalid or repeated paid pair in predecessor chain')
        skipped.update(started)
        receipts[str(folder.resolve())] = dict(started_indices=sorted(started),
            evidence_sha256={name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
                             for name in ('pilot-manifest.json', 'pilot-summary.json', 'batch-accounting.json')})
    return skipped, receipts


def check_reusable_run(folder, grade_path, pairs, model):
    manifest = json.loads((folder / 'manifest.json').read_text())
    result = json.loads((folder / 'result.json').read_text())
    graded = json.loads(grade_path.read_text())
    data = manifest['pair']
    pair = Pair(data['repo'], data['task_id'], tuple(data['features']))
    if pair.key not in {p.key for p in pairs}:
        raise ValueError('Reused run is outside the authorized selection')
    environment = resolve(pair.image)
    if (manifest.get('environment') != environment or graded.get('environment') != environment
            or manifest['model'] != asdict(model) or manifest['limits'] != LIMITS
            or manifest['member_limits'] != MEMBER_LIMITS or manifest['scheduler'] != 'async'
            or graded.get('status') != 'graded' or graded.get('backend') != BACKEND_VERSION
            or graded.get('evaluation_snapshots') != result.get('evaluation_snapshots')
            or result.get('status') != 'completed'
            or capacity_failure(result, read_trace(folder / 'trace.jsonl'))):
        raise ValueError('Reused run is not a compatible, completed and graded artifact')
    load_submitted_patches(folder, manifest, result)
    return pair.key


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selection', type=Path, required=True)
    parser.add_argument('--gates', type=Path, required=True)
    parser.add_argument('--environment-gates', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--task-concurrency', type=int, choices=(1, 2, 4), default=1)
    parser.add_argument('--repair-source', type=Path, action='append', default=[])
    parser.add_argument('--continue-batch', action='append', type=Path, default=[],
                        help='Finished predecessor segment; never rerun any started pair, including failures')
    parser.add_argument('--reuse-run', nargs=2, action='append', default=[], metavar=('RUN', 'CORRECTED_GRADE'),
                        help='Explicitly retain an existing completed attempt; no new model calls for that pair')
    authorization = parser.add_mutually_exclusive_group(required=True)
    authorization.add_argument('--authorized-twenty-paid-pairs-once', action='store_true')
    authorization.add_argument('--authorized-lite-100-paid-pairs-once', action='store_true')
    authorization.add_argument('--authorized-new-100-paid-pairs-once', action='store_true')
    authorization.add_argument('--authorized-repair-paid-pairs', type=int)
    args = parser.parse_args()
    pairs = load_selection(args.selection)
    repairing = args.authorized_repair_paid_pairs is not None
    expanding = args.authorized_new_100_paid_pairs_once
    expected = args.authorized_repair_paid_pairs if repairing else (100 if args.authorized_lite_100_paid_pairs_once or expanding else 20)
    if repairing and (expected <= 0 or args.continue_batch or args.reuse_run):
        raise ValueError('Repair authorization must be positive and cannot mix with continuation/reuse')
    if args.repair_source and not repairing:
        raise ValueError('Repair sources require explicit repair authorization')
    repairs = repair_sources(args.repair_source, pairs) if repairing else {}
    profile = 'clarified-v1' if repairing or expanding else 'official'
    if expanding and args.reuse_run:
        raise ValueError('New pairs cannot reuse old runs')
    if len(pairs) != expected:
        raise ValueError('Selection size differs from authorization')
    if not repairing and not expanding and expected == 100:
        validate_lite_selection(json.loads(args.selection.read_text()), verify_checkout(), args.reuse_run)
    if args.continue_batch and (expected != 100 or args.reuse_run):
        raise ValueError('Continuation applies only to a once-only 100-pair study')
    lock_path = ROOT / '.cache/cooperbench-paid-batch.lock'
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = lock_path.open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    validate_gates(args.environment_gates, pairs if repairing else all_task_pairs(verify_checkout()))
    validate_gates(args.gates, pairs)
    for name, sha in BUILD_WHEELS.items():
        if hashlib.sha256((ROOT / '.cache/cooperbench-wheels' / name).read_bytes()).hexdigest() != sha:
            raise ValueError('Provisioning wheel changed')
    config = load_config(ROOT / 'configs/base.yaml')
    model = replace(ModelConfig(**config['agent_model']), timeout=300, retries=0,
                    max_tokens=65536, context_window=1_000_000)
    skipped, continued = prior_attempts(args.continue_batch, pairs, json.loads(args.selection.read_text()))
    if expanding:
        validate_expansion(json.loads(args.selection.read_text()), verify_checkout(), ROOT / 'outputs/cooperbench',
                           {pairs[i].key for i in skipped})
        for folder in args.continue_batch:
            previous = json.loads((folder / 'pilot-manifest.json').read_text())
            if previous.get('benchmark_profile') != profile:
                raise ValueError('Continuation benchmark profile changed')
    reused = {}
    for source, grade_path in args.reuse_run:
        source, grade_path = Path(source).resolve(), Path(grade_path).resolve()
        key = check_reusable_run(source, grade_path, pairs, model)
        if key in reused:
            raise ValueError('Duplicate reuse input')
        reused[key] = (source, grade_path)
    args.output.mkdir(parents=True, exist_ok=False)
    frozen_source = source_digest()
    manifest = dict(source=frozen_source, revision=REVISION, backend=BACKEND_VERSION,
                    benchmark_profile=profile, repairs=repairs,
                    build_wheels=BUILD_WHEELS, pairs=[p.key for p in pairs],
                    worker_isolation=ISOLATION_VERSION, selection=json.loads(args.selection.read_text()),
                    gates=str(args.gates), environment_gates=str(args.environment_gates),
                    monetary_cap=None, attempts_per_pair=1, task_concurrency=args.task_concurrency,
                    reused_runs={k: list(map(str, v)) for k, v in reused.items()},
                    continued_batches=continued, skipped_started_indices=sorted(skipped),
                    gate_digests=gate_digests(args.gates, args.environment_gates))
    (args.output / 'pilot-manifest.json').write_text(json.dumps(manifest, indent=2))
    records = []
    for index, pair in enumerate(pairs):
        if pair.key not in reused:
            continue
        source, grade_path = reused[pair.key]
        output = args.output / str(index)
        shutil.copytree(source, output, ignore=lambda path, names: ['grade.json'] if Path(path) == source else [])
        if (source / 'grade.json').exists():
            shutil.copy2(source / 'grade.json', output / 'grade.previous.json')
        shutil.copy2(grade_path, output / 'grade.json')
        write_json(output / 'reuse.json', dict(original=str(source), corrected_grade=str(grade_path),
            original_trace_sha256=hashlib.sha256((source / 'trace.jsonl').read_bytes()).hexdigest(),
            corrected_grade_sha256=hashlib.sha256(grade_path.read_bytes()).hexdigest(), new_model_calls=0))
        graded = json.loads(grade_path.read_text())
        records.append(dict(index=index, pair=pair.key, paid_attempts=0, original_paid_attempts=1,
                            reused=True, grade=graded['correct'], batch_stop=False))
    stop = threading.Event()
    load_env()
    before = observed_balance(model)
    write_json(args.output / 'balance-before.json', before)

    def execute(item):
        index, pair = item
        sandboxes = []
        output = args.output / str(index)
        record = dict(index=index, pair=pair.key, paid_attempts=0)
        try:
            if stop.is_set():
                return dict(record, batch_stop=True, not_started=True)
            if source_digest() != frozen_source:
                raise ValueError('Source/configuration changed during batch')
            if gate_digests(args.gates, args.environment_gates) != manifest['gate_digests']:
                raise ValueError('Admission evidence changed during batch')
            validate_gates(args.gates, pairs)
            for _ in range(2):
                sb = DockerBackend().create_sandbox(pair.image, timeout=3600, workdir='/workspace/repo')
                sandboxes.append(sb)
                prepare_worker(ContainerWorkspace(sb.container, '/workspace/repo', timeout=300))
            if stop.is_set():
                return dict(record, batch_stop=True, not_started=True)
            print(json.dumps(dict(pair=pair.key, event='paid_attempt_start', index=index)), flush=True)
            record['paid_attempts'] = 1
            with (args.output / f'{index}.run.log').open('x') as log:
                run = subprocess.run([sys.executable, str(ROOT / 'scripts/cooperbench/run.py'),
                    '--repo', pair.repo, '--task', str(pair.task_id), '--features', *map(str, pair.features),
                    '--containers', *[s.container for s in sandboxes], '--output', str(output),
                    '--benchmark-profile', profile,
                    '--scheduler', 'async', '--authorized-one-paid-pair'], stdout=log, stderr=subprocess.STDOUT)
            record['run_exit'] = run.returncode
            # Frozen snapshots are on disk. Do not leave worker background jobs
            # alive while the independent evaluator runs.
            record['worker_cleanup'] = [cleanup_worker(s) for s in sandboxes]
            sandboxes.clear()
            cleanup_failed = any(not r['removed'] for r in record['worker_cleanup'])
            if cleanup_failed:
                stop.set()
            with (args.output / f'{index}.grade.log').open('x') as log:
                graded = subprocess.run([sys.executable, str(ROOT / 'scripts/cooperbench/grade.py'),
                    str(output), '--authorized-local-evaluation'], stdout=log, stderr=subprocess.STDOUT)
            record['grade_exit'] = graded.returncode
            grade = json.loads((output / 'grade.json').read_text()) if (output / 'grade.json').exists() else {}
            record['grade'] = grade.get('correct')
            result = json.loads((output / 'result.json').read_text()) if (output / 'result.json').exists() else {}
            events = [json.loads(line) for line in (output / 'trace.jsonl').read_text().splitlines()] if (output / 'trace.jsonl').exists() else []
            record['batch_stop'] = bool(cleanup_failed or run.returncode or graded.returncode or grade.get('status') != 'graded'
                                        or capacity_failure(result, events))
            if record['batch_stop']:
                stop.set()
        except Exception as error:
            record.update(batch_stop=True, infrastructure_error=str(error))
            stop.set()
        finally:
            cleanup = [cleanup_worker(s) for s in sandboxes]
            if cleanup:
                record.setdefault('worker_cleanup', []).extend(cleanup)
            if any(not row['removed'] for row in cleanup):
                record.update(batch_stop=True)
                stop.set()
        return record

    jobs = [(index, pair) for index, pair in enumerate(pairs) if pair.key not in reused and index not in skipped]
    try:
        for record in bounded_jobs(jobs, execute, args.task_concurrency, lambda r: r.get('batch_stop'), stop):
            records.append(record)
            records.sort(key=lambda r: r['index'])
            write_json(args.output / 'pilot-progress.json', records)
            print(json.dumps(record), flush=True)
    finally:
        after = observed_balance(model)
        events = [e for r in records if not r.get('reused')
                  for e in (read_trace(args.output / str(r['index']) / 'trace.jsonl')
                            if (args.output / str(r['index']) / 'trace.jsonl').exists() else [])]
        write_json(args.output / 'batch-accounting.json', dict(cost_report(events, config['pricing'], before, after),
                   task_concurrency=args.task_concurrency, reused_attempt_costs_excluded=True))
        write_json(args.output / 'pilot-summary.json', records)
    if len(records) + len(skipped) != expected or any(r.get('batch_stop') for r in records):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
