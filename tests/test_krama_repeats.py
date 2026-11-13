import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from common.io import read_json, write_json
from scripts.studies import benchmark_matrix as matrix
from scripts.studies import krama_repeats as repeats


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    manifest = read_json(repeats.MANIFEST)
    tasks = [('kramabench', SimpleNamespace(id=r['task_id']))
             for r in manifest['benchmarks']['kramabench']]
    monkeypatch.setattr(matrix, 'manifest_selections', lambda *a: tasks)
    monkeypatch.setattr(matrix.runtime, 'source_manifest', lambda: {'fixture.py': 'hash'})
    proof = tmp_path/'proof.json'
    write_json(proof, {'fixture': True})
    monkeypatch.setattr(matrix, 'runtime_preflight', lambda *a: dict(
        image_id='image', binary_sha256='binary', proofs={
            'fixture': dict(path=str(proof), sha256=matrix.digest(proof))}))
    monkeypatch.setattr(matrix.runtime, 'credential', lambda *a: pytest.fail('No credential reads'))
    args = repeats.arguments(['--output', str(tmp_path/'run'), '--proofs', str(tmp_path/'proofs')])
    plan = repeats.prepare(args)
    return args, plan


def test_default_plan_preserves_twenty_tasks_and_never_dispatches(prepared, monkeypatch, tmp_path):
    args, prepared_plan = prepared
    args.output = tmp_path/'preview'
    monkeypatch.setattr(repeats.subprocess, 'Popen', lambda *a, **kw: pytest.fail('Plan launched a process'))
    monkeypatch.setattr(matrix, 'runtime_preflight', lambda *a: pytest.fail('Default plan touched runtime'))
    plan = repeats.build_plan(args)
    assert not args.output.exists()
    assert plan['attempts'] == 180 and plan['maximum_judge_calls'] == 0
    assert plan['provider_sampling_seed'] is None
    assert plan['task_manifest_sha256'] == prepared_plan['task_manifest_sha256']
    assert [r['seed'] for r in plan['rounds']] == [0, 1, 2]
    ids = {r['task_id'] for r in prepared_plan['rounds'][0]['selections']}
    for row in plan['rounds']:
        assert len(row['selections']) == 60
        assert {r['task_id'] for r in row['selections']} == ids
        assert row['protocol']['inference_policy']['temperature'] == 0.7
        assert row['protocol']['deterministic_environment']['PYTHONHASHSEED'] == '0'
        assert row['protocol']['cpu_per_attempt'] == 8
        assert row['protocol']['solver_concurrency'] == 16
        assert '--execute' not in row['argv']
    args.with_judges = True
    assert repeats.build_plan(args)['maximum_judge_calls'] == 18


def test_schedule_seed_only_reorders_whole_task_groups():
    jobs = [('kramabench', SimpleNamespace(id=str(i)), c, Path('/fixture'))
            for i in range(20) for c in repeats.CONDITIONS]
    assert matrix.order_jobs(jobs) == jobs
    ordered = matrix.order_jobs(jobs, seed=0)
    assert ordered == matrix.order_jobs(jobs, seed=0)
    assert ordered != matrix.order_jobs(jobs, seed=1)
    assert {(b, t.id, c) for b, t, c, _ in ordered} == {(b, t.id, c) for b, t, c, _ in jobs}
    for index in range(0, 60, 3):
        assert len({t.id for _, t, _, _ in ordered[index:index+3]}) == 1
        assert tuple(c for _, _, c, _ in ordered[index:index+3]) == repeats.CONDITIONS
    with pytest.raises(ValueError, match='not both'):
        matrix.order_jobs(jobs, estimates='fixture', seed=0)


def test_duplicate_seeds_reject_before_work():
    with pytest.raises(ValueError, match='distinct seeds'):
        repeats.arguments(['--output', '/fixture', '--proofs', '/fixture', '--seeds', '1', '1', '2'])


def authorize(args):
    args.authorized_attempts = 180
    args.authorized_judges = 18 if args.with_judges else 0
    args.estimated_cost = '30'


@pytest.mark.parametrize('change', ['attempts', 'judges', 'estimate', 'source', 'proof', 'manifest', 'protocol', 'scope'])
def test_modified_or_unauthorized_plan_cannot_dispatch(prepared, monkeypatch, change):
    args, plan = prepared
    authorize(args)
    if change == 'attempts':
        args.authorized_attempts = 60
    elif change == 'judges':
        args.authorized_judges = 18
    elif change == 'estimate':
        args.estimated_cost = None
    elif change == 'source':
        monkeypatch.setattr(matrix.runtime, 'source_manifest', lambda: {'changed.py': 'hash'})
    elif change == 'proof':
        monkeypatch.setattr(matrix, 'runtime_preflight', lambda *a: dict(image_id='changed', binary_sha256='x', proofs={}))
    elif change == 'manifest':
        write_json(args.output/'task-manifest.json', {})
    elif change == 'protocol':
        write_json(args.output/(plan['rounds'][0]['name']+'-protocol.json'), {})
    else:
        args.seeds = [3, 4, 5]
    monkeypatch.setattr(repeats.subprocess, 'Popen', lambda *a, **kw: pytest.fail('Invalid plan dispatched'))
    with pytest.raises(ValueError):
        repeats.execute(args)
    assert not (args.output/'execution.json').exists()


def fake_execution(monkeypatch, args, plan, *, fail=None, source_change=False, interrupt=False):
    calls = []
    monkeypatch.setattr(repeats, 'report', lambda *a: {'fixture': True})

    class Process:
        def __init__(self, command, **kw):
            self.command = command
            calls.append(command)
            self.folder = Path(command[command.index('--output')+1])
            self.row = next(r for r in plan['rounds'] if r['name'] == self.folder.name)
            self.folder.mkdir()
            self.signals = []

        def send_signal(self, signum):
            self.signals.append(signum)

        def wait(self):
            rows = [dict(r, status='native_condition_unverified') for r in self.row['selections']]
            grades = [dict(r, status='graded', grade={'score': 1}, judge_calls=0) for r in self.row['selections']]
            if fail != 'missing':
                if fail == 'duplicate':
                    rows[-1] = rows[0]
                if fail == 'unknown':
                    grades[0]['status'] = 'judge_outcome_unknown'
                write_json(self.folder/'summary.json', dict(rows=rows, grades=grades, interrupted=fail=='interrupted'))
            if fail == 'balance':
                write_json(self.folder/'balance-paused.json', {})
            if source_change:
                monkeypatch.setattr(matrix.runtime, 'source_manifest', lambda: {'changed': 'source'})
            if interrupt:
                repeats.signal.getsignal(repeats.signal.SIGTERM)(repeats.signal.SIGTERM, None)
                assert self.signals
            return 1  # Audit failure does not discard a completed attempt.

    monkeypatch.setattr(repeats.subprocess, 'Popen', Process)
    return calls


def test_three_rounds_are_sequential_and_never_reexecuted(prepared, monkeypatch):
    args, plan = prepared
    authorize(args)
    calls = fake_execution(monkeypatch, args, plan)
    assert repeats.execute(args) == 0
    assert len(calls) == 3
    for index, command in enumerate(calls):
        assert command[command.index('--authorized-attempts')+1] == '60'
        assert command[command.index('--authorized-judges')+1] == '0'
        assert float(command[command.index('--estimated-cost')+1]) == [30, 20, 10][index]
        assert '--retain-started-from' not in command
    assert read_json(args.output/'execution-result.json')['complete'] is True
    with pytest.raises((ValueError, FileExistsError)):
        repeats.execute(args)
    assert len(calls) == 3


def test_explicit_paid_judge_plan_limits_each_round_to_six(prepared, monkeypatch):
    args, _ = prepared
    args.with_judges = True
    plan = repeats.build_plan(args, check_runtime=True)
    write_json(args.output/'plan.json', plan)
    authorize(args)
    calls = fake_execution(monkeypatch, args, plan)
    assert repeats.execute(args) == 0
    assert len(calls) == 3
    assert all(command[command.index('--authorized-judges')+1] == '6' for command in calls)


@pytest.mark.parametrize('failure', ['missing', 'duplicate', 'unknown', 'interrupted', 'balance'])
def test_incomplete_round_stops_later_rounds_without_retry(prepared, monkeypatch, failure):
    args, plan = prepared
    authorize(args)
    calls = fake_execution(monkeypatch, args, plan, fail=failure)
    assert repeats.execute(args) == 1
    assert len(calls) == 1
    assert read_json(args.output/'execution-result.json')['complete'] is False


def test_source_change_between_rounds_fails_closed(prepared, monkeypatch):
    args, plan = prepared
    authorize(args)
    calls = fake_execution(monkeypatch, args, plan, source_change=True)
    with pytest.raises(ValueError, match='Source changed'):
        repeats.execute(args)
    assert len(calls) == 1


@pytest.mark.parametrize('change', ['protocol', 'proof'])
def test_inputs_modified_between_rounds_prevent_next_dispatch(prepared, monkeypatch, change):
    args, plan = prepared
    authorize(args)
    calls = fake_execution(monkeypatch, args, plan)
    original = repeats.round_complete
    def modify(folder, expected):
        if change == 'protocol':
            write_json(args.output/(plan['rounds'][1]['name']+'-protocol.json'), {})
        else:
            write_json(Path(plan['rounds'][1]['runtime_binding']['proofs']['fixture']['path']), {})
        return original(folder, expected)
    monkeypatch.setattr(repeats, 'round_complete', modify)
    with pytest.raises(ValueError, match='changed between rounds'):
        repeats.execute(args)
    assert len(calls) == 1


def test_launch_failure_leaves_one_shot_receipt_without_retry(prepared, monkeypatch):
    args, _ = prepared
    authorize(args)
    calls = []
    monkeypatch.setattr(repeats, 'report', lambda *a: {})
    def fail(*a, **kw):
        calls.append(a)
        raise OSError('Synthetic launch failure')
    monkeypatch.setattr(repeats.subprocess, 'Popen', fail)
    with pytest.raises(OSError):
        repeats.execute(args)
    with pytest.raises(FileExistsError):
        repeats.execute(args)
    assert len(calls) == 1
    assert read_json(args.output/'execution-result.json')['complete'] is False


def test_interrupt_does_not_start_next_round(prepared, monkeypatch):
    args, plan = prepared
    authorize(args)
    calls = fake_execution(monkeypatch, args, plan, interrupt=True)
    assert repeats.execute(args) == 1
    assert len(calls) == 1
    assert read_json(args.output/'execution-result.json')['interrupted'] is True


def score_records(plan):
    return [[dict(row, score=score, native_audit_passed=True) for row in r['selections']]
            for r, score in zip(plan['rounds'], (0, 0.5, 1))]


def test_aggregate_equal_weights_sd_and_shared_paired_cohort(prepared):
    _, plan = prepared
    records = score_records(plan)
    records[1][0]['native_audit_passed'] = False
    result = repeats.aggregate(plan, records)
    for group in result['raw']:
        assert group['round_means'] == [0, 0.5, 1]
        assert group['mean'] == 0.5 and group['sample_sd'] == 0.5
        assert group['score_consistency_rate'] == 0
    assert len(result['paired_native_audit']['included_tasks']) == 19
    assert all(g['tasks_per_round'] == 19 for g in result['paired_native_audit']['groups'])


def test_unknown_scores_are_not_dropped_or_zero_imputed(prepared):
    _, plan = prepared
    records = score_records(plan)
    records[0][0]['score'] = None
    records[2][0]['native_audit_passed'] = None
    group = repeats.aggregate(plan, records)['raw'][0]
    assert group['mean'] is None and group['sample_sd'] is None
    assert group['known_scores'] == [19, 20, 20]
    assert group['consistency_measured_tasks'] == 19
    assert next(r for r in group['per_task'] if r['task_id'] == records[0][0]['task_id'])['score_consistent'] is None
    missing = repeats.aggregate(plan, records[:2])
    assert missing['raw'][0]['mean'] is None
    assert missing['paired_native_audit']['included_tasks'] == []


def test_report_retains_accounting_and_flags_missing_rounds(prepared, monkeypatch):
    args, plan = prepared
    records = score_records(plan)
    def collect(path):
        index = next(r['index']-1 for r in plan['rounds'] if r['name'] == path.name)
        if index == 1:
            raise ValueError('Missing round')
        return dict(rows=records[index], account_delta={'CNY': 1}, groups=[{'known_cost': 2}])
    monkeypatch.setattr(repeats.matched_matrix_report, 'collect', collect)
    result = repeats.report(args.output)
    assert len(result['round_accounting']) == 2
    assert len(result['unavailable_rounds']) == 1
    assert result['raw'][0]['mean'] is None


def test_report_cli_needs_no_proof_or_runtime(prepared, monkeypatch, capsys):
    args, _ = prepared
    monkeypatch.setattr(repeats, 'build_plan', lambda *a, **kw: pytest.fail('Report checked runtime'))
    assert repeats.main(['--output', str(args.output), '--report']) == 0
    result = json.loads(capsys.readouterr().out)
    assert len(result['unavailable_rounds']) == 3


def reuse_plan(prepared, monkeypatch):
    args, original = prepared
    args.output = args.output.with_name('reuse-run')
    args.reuse_single = [args.output.parent/'old-first', args.output.parent/'old-second']
    references = {}
    for index, path in enumerate(args.reuse_single):
        path.mkdir()
        evidence = path/'fixture.json'
        write_json(evidence, {'round': index})
        rows = [dict(r, score=index/2, native_audit_passed=True) for r in original['rounds'][0]['selections']
                if r['backend'] == repeats.CONDITIONS[0]]
        references[path] = dict(run=str(path), rows=rows,
            native_attempts={r['task_id']: f'session-{index}-{r["task_id"]}' for r in rows},
            files_sha256={str(evidence): matrix.digest(evidence)}, original_accounting=[],
            new_solver_calls=0, new_judge_calls=0)
    monkeypatch.setattr(repeats, 'single_reference', lambda path, manifest: references[path])
    args.with_judges = True
    plan = repeats.prepare(args)
    return args, plan, references


def test_reuse_two_single_rounds_dispatches_only_missing_round(prepared, monkeypatch):
    args, plan, _ = reuse_plan(prepared, monkeypatch)
    assert plan['attempts'] == 140 and plan['maximum_judge_calls'] == 14
    assert [len(r['selections']) for r in plan['rounds']] == [40, 40, 60]
    assert [r['authorized_judges'] for r in plan['rounds']] == [4, 4, 6]
    assert all(r['backend'] != repeats.CONDITIONS[0] for round_ in plan['rounds'][:2] for r in round_['selections'])
    args.authorized_attempts, args.authorized_judges, args.estimated_cost = 140, 14, '35'
    calls = fake_execution(monkeypatch, args, plan)
    assert repeats.execute(args) == 0
    assert [int(c[c.index('--authorized-attempts')+1]) for c in calls] == [40, 40, 60]
    assert [int(c[c.index('--authorized-judges')+1]) for c in calls] == [4, 4, 6]
    assert [float(c[c.index('--estimated-cost')+1]) for c in calls] == [35, 25, 15]


def test_reused_single_is_three_distinct_observations_not_copied(prepared, monkeypatch):
    _, plan, _ = reuse_plan(prepared, monkeypatch)
    records = score_records(plan)
    report = repeats.aggregate(plan, records)
    single = report['raw'][0]
    assert single['round_means'] == [0, 0.5, 1]
    assert single['mean'] == 0.5 and single['sample_sd'] == 0.5
    assert report['single_reuse']['retained_rounds'] == 2
    assert len(report['paired_native_audit']['included_tasks']) == 20
    records[0].append(plan['single_references'][0]['rows'][0])
    with pytest.raises(ValueError, match='duplicate'):
        repeats.aggregate(plan, records)


def test_same_single_attempt_cannot_be_reused_twice(prepared, monkeypatch):
    args, _, references = reuse_plan(prepared, monkeypatch)
    references[args.reuse_single[1]]['native_attempts'] = references[args.reuse_single[0]]['native_attempts']
    with pytest.raises(ValueError, match='same Single attempt'):
        repeats.build_plan(args)


def test_reused_single_evidence_is_bound_before_dispatch(prepared, monkeypatch):
    args, plan, references = reuse_plan(prepared, monkeypatch)
    args.authorized_attempts, args.authorized_judges, args.estimated_cost = 140, 14, '35'
    first = references[args.reuse_single[0]]
    Path(next(iter(first['files_sha256']))).write_text('changed')
    calls = fake_execution(monkeypatch, args, plan)
    with pytest.raises(ValueError, match='Single evidence changed'):
        repeats.execute(args)
    assert calls == []


@pytest.mark.parametrize('function', ['retained_attempts', 'upstream_recovery', 'batch_chain'])
def test_pruned_evidence_never_becomes_unstarted_retry_scope(tmp_path, function):
    write_json(tmp_path/'evidence-pruned.json', {'continuation_prohibited': True})
    with pytest.raises(ValueError, match='pruned evidence'):
        if function == 'batch_chain':
            list(matrix.batch_chain(tmp_path))
        else:
            getattr(matrix, function)(tmp_path, [], {}, 'manifest-hash')


def reference_fixture(prepared, monkeypatch):
    args, plan = prepared
    manifest = read_json(repeats.MANIFEST)
    root = args.output.parent/'recorded-single'
    rows, grades = [], []
    for task in plan['task_ids']:
        folder = root/'solvers/kramabench'/task/repeats.CONDITIONS[0]/task/repeats.CONDITIONS[0]
        write_json(folder/'report.json', dict(cli={'native_result': {'session_id': 'native-'+task}}))
        (folder/'gateway-requests.jsonl').write_text(json.dumps(dict(event='dispatched', route='/anthropic/v1/messages',
            request_parameters=dict(thinking='disabled', temperature=plan['rounds'][0]['protocol']['inference_policy']['temperature'])))+'\n')
        rows.append(dict(benchmark='kramabench', task_id=task, backend=repeats.CONDITIONS[0],
            status='cli_exited', native_audit_passed=True, score=0, infra_degraded=False, evidence=str(folder),
            seconds=None, total_usd_offpeak=None, model_requests=1))
        grades.append(dict(backend=repeats.CONDITIONS[0], task_id=task, judge_calls=0))
    summary = dict(authorization=dict(task_manifest_sha256=matrix.digest(repeats.MANIFEST),
        protocol_settings=plan['rounds'][0]['protocol']), rows=rows, grades=grades)
    write_json(root/'summary.json', summary)
    monkeypatch.setattr(repeats.matched_matrix_report, 'collect', lambda path: {'rows': rows})
    return root, manifest, rows, summary


def test_retained_single_preserves_zero_scores_and_binds_original_payloads(prepared, monkeypatch):
    root, manifest, rows, _ = reference_fixture(prepared, monkeypatch)
    result = repeats.single_reference(root, manifest)
    assert len(result['native_attempts']) == 20
    assert len(result['files_sha256']) == 41
    assert all(r['score'] == 0 for r in result['rows'])
    assert result['new_solver_calls'] == result['new_judge_calls'] == 0


def test_historical_temperature_one_stays_readable_but_cannot_mix_into_new_plan(prepared, monkeypatch):
    root,manifest,rows,summary=reference_fixture(prepared,monkeypatch)
    old_policy=dict(thinking='disabled',temperature=1.0,effort=None)
    summary['authorization']['protocol_settings']['inference_policy']=old_policy
    write_json(root/'summary.json',summary)
    for row in rows:
        (Path(row['evidence'])/'gateway-requests.jsonl').write_text(json.dumps(dict(
            event='dispatched',route='/anthropic/v1/messages',
            request_parameters=dict(thinking='disabled',temperature=1.0)))+'\n')
    retained=repeats.single_reference(root,manifest)
    assert retained['inference_policy']==old_policy
    args,_=prepared;args.reuse_single=[root,root.parent/'other-retained']
    monkeypatch.setattr(repeats,'single_reference',lambda *a:retained)
    with pytest.raises(ValueError,match='do not mix temperatures'):repeats.build_plan(args)


@pytest.mark.parametrize('corruption', ['wire-temperature', 'duplicate-session', 'audit', 'score',
                                      'missing-task', 'cpu', 'manifest', 'missing-judge'])
def test_retained_single_rejects_incompatible_or_incomplete_evidence(prepared, monkeypatch, corruption):
    root, manifest, rows, summary = reference_fixture(prepared, monkeypatch)
    folder = Path(rows[0]['evidence'])
    if corruption == 'wire-temperature':
        (folder/'gateway-requests.jsonl').write_text(json.dumps(dict(event='dispatched', route='/anthropic/v1/messages',
            request_parameters=dict(thinking='disabled', temperature=0.0)))+'\n')
    elif corruption == 'duplicate-session':
        second = read_json(Path(rows[1]['evidence'])/'report.json')
        write_json(folder/'report.json', second)
    elif corruption == 'audit':
        rows[0]['native_audit_passed'] = False
    elif corruption == 'score':
        rows[0]['score'] = None
    elif corruption == 'missing-task':
        rows.pop()
    elif corruption == 'cpu':
        summary['authorization']['protocol_settings']['cpu_per_attempt'] = 2
    elif corruption == 'manifest':
        summary['authorization']['task_manifest_sha256'] = 'wrong'
    else:
        summary['grades'][0].update(judge_calls=1, grading_artifact=str(root/'missing-judge'))
    write_json(root/'summary.json', summary)
    with pytest.raises(ValueError):
        repeats.single_reference(root, manifest)
