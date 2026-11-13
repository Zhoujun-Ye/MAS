"""Three independent repeats of the frozen Krama Random20 comparison."""

import argparse
from contextlib import redirect_stdout
import io
import json
import math
from pathlib import Path
import signal
import statistics
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common.io import fingerprint, read_json, write_json
from common.journal import exclusive
from harness.runtime_support import runtime
from harness.runtime_support.admission import amount
from scripts.studies import benchmark_matrix as matrix
from scripts.studies import matched_matrix_report

MANIFEST = Path(__file__).resolve().parents[2] / 'docs/studies/krama-random20-manifest.json'
CONDITIONS = ('claude-code-single-agent', 'native', 'claude-code-subagents')
ATTEMPTS = 180


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('/home/zhoujunye/mas-data'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--proofs', type=Path)
    parser.add_argument('--image', default='mas/research-benchmarks:20261111-sqlite-v2')
    parser.add_argument('--credentials', type=Path, default=Path('/home/zhoujunye/mas/.env'))
    parser.add_argument('--seeds', type=int, nargs=3, default=(0, 1, 2),
                        help='Three distinct dispatch-order seeds, NOT model sampling seeds')
    parser.add_argument('--concurrency', type=int, choices=range(1, 257), default=16)
    parser.add_argument('--with-judges', action='store_true', help='Plan at most 18 one-call semantic grades')
    parser.add_argument('--reuse-single', type=Path, nargs=2, metavar=('FIRST_BATCH', 'SECOND_BATCH'),
                        help='Reuse two complete independent Single rounds; dispatch only the missing third')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--prepare', action='store_true', help='Free runtime checks and freeze plan; no paid calls')
    mode.add_argument('--execute', action='store_true', help='Execute an unchanged prepared plan; requires new authorization')
    mode.add_argument('--report', action='store_true', help='Read retained results only')
    parser.add_argument('--authorized-attempts', type=int)
    parser.add_argument('--authorized-judges', type=int, default=0)
    parser.add_argument('--estimated-cost', help='Positive total remaining CNY estimate, not a spending cap')
    parser.add_argument('--balance-reserve', default='5')
    args = parser.parse_args(argv)
    if args.proofs is None and not args.report:
        parser.error('--proofs is required unless reading --report')
    if len(set(args.seeds)) != 3:
        raise ValueError('Require three distinct seeds')
    if amount(args.balance_reserve) < 0:
        raise ValueError('Balance reserve cannot be negative')
    for name in ('root', 'output', 'proofs', 'credentials'):
        value = getattr(args, name)
        if value is not None:
            setattr(args, name, value.resolve())
    if args.reuse_single:
        args.reuse_single = [path.resolve() for path in args.reuse_single]
        if len(set(args.reuse_single)) != 2 or any(
                args.output.is_relative_to(path) or path.is_relative_to(args.output) for path in args.reuse_single):
            raise ValueError('Reuse two distinct batches outside the new output directory')
    return args


def single_reference(path, manifest):
    """Freeze recorded Single results, never regrade, select by score or copy attempts."""
    summary = read_json(path/'summary.json')
    if not summary:
        raise ValueError('Missing retained Single batch summary')
    settings = summary['authorization']['protocol_settings']
    expected = manifest['baseline_settings']
    policy = settings.get('inference_policy')
    if (summary['authorization'].get('task_manifest_sha256') != matrix.digest(MANIFEST)
            or policy not in (dict(thinking='disabled', temperature=0.7, effort=None), runtime.inference_configuration())
            or settings.get('cpu_per_attempt') != 8 or settings.get('compute_threads') != 4
            or settings.get('timeout_seconds_by_benchmark', {}).get('kramabench') != 3600
            or settings.get('organization_sha256', {}).get(CONDITIONS[0]) != expected['organization_sha256'][CONDITIONS[0]]):
        raise ValueError('Retained Single task/inference/resource/prompt protocol differs')
    collected = matched_matrix_report.collect(path)
    rows = [r for r in collected['rows'] if r['backend'] == CONDITIONS[0]]
    ids = {r['task_id'] for r in manifest['benchmarks']['kramabench']}
    if (len(rows) != 20 or {r['task_id'] for r in rows} != ids or any(
            r['benchmark'] != 'kramabench' or r['status'] != 'cli_exited'
            or r['native_audit_passed'] is not True or not finite_score(r.get('score'))
            or r.get('infra_degraded') is not False for r in rows)):
        raise ValueError('Require exactly twenty complete, scored, audited Single attempts')
    files = {str(path/'summary.json'): matrix.digest(path/'summary.json')}
    if (path/'authorization.json').exists():
        files[str(path/'authorization.json')] = matrix.digest(path/'authorization.json')
    if (path/'evidence-pruned.json').exists():
        files[str(path/'evidence-pruned.json')] = matrix.digest(path/'evidence-pruned.json')
    attempts = {}
    grades = {g['task_id']: g for g in summary['grades'] if g['backend'] == CONDITIONS[0]}
    for row in rows:
        folder = Path(row['evidence'])
        if not folder.resolve().is_relative_to((path/'solvers').resolve()):
            raise ValueError('Retained Single evidence lies outside its original batch')
        report = read_json(folder/'report.json', {})
        session = report.get('cli', {}).get('native_result', {}).get('session_id')
        if not isinstance(session, str) or not session:
            raise ValueError('Retained Single lacks a native attempt identity')
        attempts[row['task_id']] = session
        ledger = folder/'gateway-requests.jsonl'
        requests = [json.loads(line) for line in ledger.read_text().splitlines()]
        model = [r for r in requests if r.get('event') == 'dispatched' and r.get('route') == '/anthropic/v1/messages']
        if not model or any(r.get('request_parameters', {}).get('thinking') != 'disabled'
                or r.get('request_parameters', {}).get('temperature') != policy['temperature'] for r in model):
            raise ValueError('Retained Single lacks matching observed thinking/temperature evidence')
        roots = [folder]
        artifact = grades[row['task_id']].get('grading_artifact')
        if artifact:
            if grades[row['task_id']].get('judge_calls') and not (Path(artifact)/'result.json').is_file():
                raise ValueError('Retained paid Single grade artifact is missing')
            roots.append(Path(artifact))
        for root in roots:
            for entry in root.rglob('*'):
                if entry.is_file() and not entry.is_symlink():
                    files[str(entry)] = matrix.digest(entry)
    if len(set(attempts.values())) != 20:
        raise ValueError('Retained Single native attempts are not independent')
    return dict(run=str(path), rows=rows, native_attempts=attempts, files_sha256=files,
                inference_policy=policy,
                original_accounting=matched_matrix_report.summarize(rows), new_solver_calls=0, new_judge_calls=0)


def build_plan(args, *, check_runtime=False):
    manifest = read_json(MANIFEST)
    if set(manifest['benchmarks']) != {'kramabench'} or len(manifest['benchmarks']['kramabench']) != 20:
        raise ValueError('Expected the unchanged frozen Krama Random20 manifest')
    references = [single_reference(path, manifest) for path in (args.reuse_single or [])]
    if any(r.get('inference_policy',runtime.inference_configuration()) != runtime.inference_configuration() for r in references):
        raise ValueError('Retained Single sampling policy differs from the current default; do not mix temperatures')
    if references and set(references[0]['native_attempts'].values()) & set(references[1]['native_attempts'].values()):
        raise ValueError('The same Single attempt cannot count as two independent repeats')
    rounds = []
    for index, seed in enumerate(args.seeds, 1):
        conditions = CONDITIONS[1:] if references and index <= 2 else CONDITIONS
        name = f'round-{index:02d}-seed-{seed}'
        base = ['--root', str(args.root), '--output', str(args.output/name),
                '--proofs', str(args.proofs), '--image', args.image,
                '--credentials', str(args.credentials), '--benchmarks', 'kramabench',
                '--conditions', *conditions, '--tasks-per-benchmark', '20',
                '--task-manifest', str(MANIFEST), '--effort', 'none',
                '--concurrency', str(args.concurrency), '--judge-concurrency', '2',
                '--cpus', '8', '--compute-threads', '4', '--record-resources',
                '--schedule-seed', str(seed), '--balance-reserve', args.balance_reserve]
        output = io.StringIO()
        with redirect_stdout(output):
            matrix.main(base + (['--check-runtime'] if check_runtime else []))
        planned = json.loads(output.getvalue())
        settings = planned['protocol_settings']
        if (planned['attempts'] != 20*len(conditions) or settings['inference_policy'] !=
                runtime.inference_configuration() or
                settings['organization_sha256'] != {c: manifest['baseline_settings']['organization_sha256'][c] for c in conditions}):
            raise ValueError('Frozen prompts or current thinking-off sampling policy changed')
        ready = planned.get('runtime_preflight')
        binding = None if ready is None else {k: ready[k] for k in ('image_id', 'binary_sha256', 'proofs')}
        rounds.append(dict(index=index, seed=seed, name=name, protocol=settings,
            authorized_judges=2*len(conditions) if args.with_judges else 0,
            selections=planned['selections'], runtime_binding=binding,
            argv=base + ['--protocol-settings', str(args.output/(name+'-protocol.json'))]))
    return dict(kind='krama-random20-three-repeats-v1', attempts=140 if references else ATTEMPTS,
        maximum_judge_calls=(14 if references else 18) if args.with_judges else 0, retries=0,
        task_ids=[r['task_id'] for r in manifest['benchmarks']['kramabench']],
        single_references=references,
        seed_scope='Independent repeats; seeds control task-group dispatch order only',
        provider_sampling_seed=None, task_manifest_sha256=matrix.digest(MANIFEST),
        source_manifest=runtime.source_manifest(), rounds=rounds,
        round_execution='sequential; each round has independent workspaces and bounded parallel solvers',
        budget_policy=dict(currency='CNY', reserve=args.balance_reserve, safety_factor='1.5', monetary_cap=None))


def prepare(args):
    if args.output.exists():
        raise ValueError('Preparation requires a fresh output directory')
    plan = build_plan(args, check_runtime=True)
    args.output.mkdir(parents=True, exist_ok=False, mode=0o700)
    write_json(args.output/'task-manifest.json', read_json(MANIFEST))
    for row in plan['rounds']:
        write_json(args.output/(row['name']+'-protocol.json'), row['protocol'])
    write_json(args.output/'plan.json', plan)
    return plan


def validate_prepared(args):
    plan = read_json(args.output/'plan.json')
    attempts = 140 if args.reuse_single else ATTEMPTS
    judges = (14 if args.reuse_single else 18) if args.with_judges else 0
    if args.authorized_attempts != attempts or args.authorized_judges != judges:
        raise ValueError(f'Require exactly {attempts} authorized solvers and {judges} authorized judges')
    if args.estimated_cost is None or amount(args.estimated_cost) <= 0:
        raise ValueError('Require a positive total --estimated-cost; this is not a spending cap')
    if not plan or plan != build_plan(args, check_runtime=True):
        raise ValueError('Prepared source, scope, configuration or runtime proofs changed; prepare a fresh plan')
    if read_json(args.output/'task-manifest.json') != read_json(MANIFEST):
        raise ValueError('Prepared task manifest changed')
    for row in plan['rounds']:
        if read_json(args.output/(row['name']+'-protocol.json')) != row['protocol']:
            raise ValueError('Prepared round protocol changed')
        if (args.output/row['name']).exists():
            raise ValueError('Round output already exists; no retries or automatic continuation')
    return plan


def round_complete(folder, expected):
    summary = read_json(folder/'summary.json')
    if not summary or summary.get('interrupted') is not False:
        return False
    if any((folder/name).exists() for name in (
            'failure.json', 'balance-paused.json', 'fatal-provider-error.json', 'monitor-error.json')):
        return False
    key = lambda r: (r['benchmark'], r['task_id'], r['backend'])
    scope = {key(r) for r in expected}
    bad = {'not_started', 'dispatch_unknown', 'harness_error', 'runtime_error',
           'missing_summary', 'missing_predictions', 'grading_failed', 'judge_error',
           'solver_outcome_unknown', 'grading_outcome_unknown', 'judge_outcome_unknown'}
    for field in ('rows', 'grades'):
        rows = summary.get(field, [])
        if len(rows) != len(scope) or {key(r) for r in rows} != scope:
            return False
        if any(r.get('status') in bad or r.get('infra_degraded') or r.get('fatal_provider_error') for r in rows):
            return False
    return True


def validate_round_inputs(args, plan, row):
    if runtime.source_manifest() != plan['source_manifest']:
        raise ValueError('Source changed between rounds; later rounds not dispatched')
    if (matrix.digest(MANIFEST) != plan['task_manifest_sha256'] or
            read_json(args.output/(row['name']+'-protocol.json')) != row['protocol']):
        raise ValueError('Task manifest or protocol changed between rounds')
    for proof in row['runtime_binding']['proofs'].values():
        if matrix.digest(Path(proof['path'])) != proof['sha256']:
            raise ValueError('Native proof changed between rounds')
    for reference in plan.get('single_references', []):
        for filename, expected in reference['files_sha256'].items():
            if matrix.digest(Path(filename)) != expected:
                raise ValueError('Retained Single evidence changed between rounds')


def execute(args):
    # All free validation precedes the irreversible one-shot dispatch marker.
    plan = validate_prepared(args)
    with exclusive(args.output/'controller.lock'):
        with (args.output/'execution.json').open('x') as receipt:
            json.dump(dict(plan_sha256=fingerprint(plan), authorized_attempts=plan['attempts'],
                authorized_judges=args.authorized_judges, estimated_cost=args.estimated_cost,
                started_at=runtime.now(), retries=0), receipt, indent=2)
        active = None
        stopped = False
        results = []

        def interrupt(signum, _frame):
            nonlocal stopped
            stopped = True
            if active is not None:
                active.send_signal(signum)

        previous = {s: signal.signal(s, interrupt) for s in (signal.SIGINT, signal.SIGTERM)}
        try:
            for row in plan['rounds']:
                if stopped:
                    break
                validate_round_inputs(args, plan, row)
                # Admit enough balance for the still-unstarted scope, not just this round.
                remaining_slots = sum(len(r['selections']) for r in plan['rounds'] if r['index'] >= row['index'])
                remaining = amount(args.estimated_cost) * remaining_slots / plan['attempts']
                command = [sys.executable, '-m', 'scripts.studies.benchmark_matrix', *row['argv'],
                    '--execute', '--authorized-attempts', str(len(row['selections'])), '--authorized-judges',
                    str(row['authorized_judges']), '--estimated-cost', str(remaining)]
                write_json(args.output/'progress.json', dict(active_round=row['name'], completed=results))
                with (args.output/(row['name']+'.log')).open('x') as log:
                    active = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[2],
                                              stdout=log, stderr=subprocess.STDOUT)
                    if stopped:
                        active.send_signal(signal.SIGTERM)
                    code = active.wait()
                    active = None
                complete = round_complete(args.output/row['name'], row['selections'])
                calls = read_json(args.output/row['name']/'summary.json', {}).get('grades', [])
                counts = [g.get('judge_calls') for g in calls]
                known_calls = sum(c for c in counts if type(c) is int and c >= 0)
                if (known_calls > row['authorized_judges'] or
                        any(type(c) is not int or c < 0 for c in counts)):
                    complete = False
                results.append(dict(round=row['name'], returncode=code, complete=complete))
                write_json(args.output/'progress.json', dict(active_round=None, completed=results))
                # Exit 1 may mean a retained model/audit failure, not an interrupted batch.
                if code not in (0, 1) or not complete:
                    break
        finally:
            if active is not None:
                active.send_signal(signal.SIGTERM)
                active.wait()  # The matrix owns cleanup; do not orphan paid child processes.
            for signum, handler in previous.items():
                signal.signal(signum, handler)
            write_json(args.output/'execution-result.json', dict(rounds=results,
                interrupted=stopped, complete=len(results)==3 and all(r['complete'] for r in results),
                finished_at=runtime.now()))
            write_json(args.output/'repeat-report.json', report(args.output))
        return 0 if not stopped and len(results)==3 and all(r['complete'] for r in results) else 1


def finite_score(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1


def aggregate(plan, records):
    """Equal-weight repeats, never best-of-N; unknown scores do not become zeros."""
    task_ids = plan.get('task_ids') or [r['task_id'] for r in plan['rounds'][0]['selections'] if r['backend']==CONDITIONS[0]]
    expected = {(t, c) for t in task_ids for c in CONDITIONS}
    by_round = []
    for rows in records:
        keys = [(r['task_id'], r['backend']) for r in rows]
        if len(keys) != len(set(keys)) or set(keys)-expected:
            raise ValueError('Unexpected or duplicate repeat result cells')
        by_round.append(dict(zip(keys, rows)))
    for index, reference in enumerate(plan.get('single_references', [])):
        if index >= len(by_round):
            by_round.append({})
        for row in reference['rows']:
            key = (row['task_id'], row['backend'])
            if key in by_round[index]:
                raise ValueError('Retained Single would duplicate a newly dispatched result')
            by_round[index][key] = row
    while len(by_round) < 3:
        by_round.append({})
    if len(by_round) != 3:
        raise ValueError('Expected three rounds')
    paired = [t for t in task_ids if all(
        grid.get((t, c), {}).get('native_audit_passed') is True for grid in by_round for c in CONDITIONS)]

    def view(ids):
        groups = []
        for condition in CONDITIONS:
            means = []
            known_counts = []
            for grid in by_round:
                scores = [grid.get((t, condition), {}).get('score') for t in ids]
                known_counts.append(sum(finite_score(s) for s in scores))
                means.append(statistics.mean(scores) if scores and all(finite_score(s) for s in scores) else None)
            complete = all(m is not None for m in means)
            consistency = []
            for task in ids:
                values = [grid.get((task, condition), {}).get('score') for grid in by_round]
                consistency.append(dict(task_id=task, scores=values,
                    score_consistent=len(set(values))==1 if all(finite_score(s) for s in values) else None))
            measured = [r['score_consistent'] for r in consistency if r['score_consistent'] is not None]
            groups.append(dict(condition=condition, tasks_per_round=len(ids), known_scores=known_counts,
                round_means=means, mean=statistics.mean(means) if complete else None,
                sample_sd=statistics.stdev(means) if complete else None,
                score_consistency_rate=sum(measured)/len(measured) if measured else None,
                consistency_measured_tasks=len(measured), per_task=consistency))
        return groups

    return dict(kind='krama-three-repeats-report-v1', raw=view(task_ids),
        single_reuse=dict(retained_rounds=len(plan.get('single_references', [])),
            original_runs=[r['run'] for r in plan.get('single_references', [])],
            original_accounting=[r['original_accounting'] for r in plan.get('single_references', [])],
            policy='Each distinct historical Single attempt counts once; no new call or repeated billing. '
                   'Historical Single and new MAS are not contemporaneous.'),
        paired_native_audit=dict(included_tasks=paired,
            excluded_tasks=[t for t in task_ids if t not in paired], groups=view(paired)),
        limitations=['Seeds fix dispatch order only, not provider sampling.',
            'Score consistency is not answer or trajectory agreement.',
            'Three repeated development-set runs are descriptive, not independent final tests.',
            'No best-of-three selection; missing scores remain unknown; all costs stay in original round receipts.'])


def report(folder):
    plan = read_json(folder/'plan.json')
    if not plan:
        raise ValueError('A prepared plan is required')
    records, errors, accounting = [], [], []
    for row in plan['rounds']:
        path = folder/row['name']
        try:
            collected = matched_matrix_report.collect(path)
            records.append(collected['rows'])
            accounting.append(dict(round=row['name'], account_delta=collected.get('account_delta'),
                                   groups=collected['groups']))
        except (OSError, ValueError, KeyError, TypeError) as error:
            records.append([])
            errors.append(dict(round=row['name'], error_type=type(error).__name__))
    return dict(aggregate(plan, records), unavailable_rounds=errors, round_accounting=accounting,
                accounting_scope='Original account intervals and known partial estimates; not complete invoices')


def main(argv=None):
    args = arguments(argv)
    if args.report:
        print(json.dumps(report(args.output), indent=2))
        return 0
    if args.execute:
        return execute(args)
    plan = prepare(args) if args.prepare else build_plan(args)
    print(json.dumps(plan, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
