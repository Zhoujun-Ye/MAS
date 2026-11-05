import json
from types import SimpleNamespace

import pytest

from scripts.server import benchmark_matrix as matrix


def fixture_manifest(monkeypatch):
    pools = {b: [SimpleNamespace(id=f'{b}-{i}', question=f'public-{i}', category='test') for i in range(20)]
             for b in matrix.BENCHMARKS}
    monkeypatch.setattr(matrix, 'dc_tasks', lambda p: pools['dataclawbench'])
    monkeypatch.setattr(matrix, 'hdr_tasks', lambda p: pools['hybriddeepresearch'])
    monkeypatch.setattr(matrix, 'krama_tasks', lambda p: (pools['kramabench'], {}))
    manifest = dict(kind='validation20-v1', benchmarks={b: [dict(task_id=t.id, task_sha256=matrix.task_fingerprint(b, t))
                                                        for t in tasks] for b, tasks in pools.items()})
    return pools, manifest


def test_frozen_extension_has_no_overlap_and_keeps_order(tmp_path, monkeypatch):
    _, manifest = fixture_manifest(monkeypatch)
    initial = matrix.manifest_selections(tmp_path, manifest, 0, 10)
    extension = matrix.manifest_selections(tmp_path, manifest, 10, 10)
    assert len(initial) == len(extension) == 30
    assert not {(b, t.id) for b, t in initial} & {(b, t.id) for b, t in extension}
    for b in matrix.BENCHMARKS:
        assert [t.id for bench, t in extension if bench == b] == [f'{b}-{i}' for i in range(10, 20)]


def test_frozen_task_changes_and_duplicates_are_rejected(tmp_path, monkeypatch):
    pools, manifest = fixture_manifest(monkeypatch)
    pools['hybriddeepresearch'][0].question = 'changed'
    with pytest.raises(ValueError, match='changed'):
        matrix.manifest_selections(tmp_path, manifest, 10, 10)
    pools, manifest = fixture_manifest(monkeypatch)
    manifest['benchmarks']['dataclawbench'][1] = manifest['benchmarks']['dataclawbench'][0]
    with pytest.raises(ValueError, match='unique'):
        matrix.manifest_selections(tmp_path, manifest, 10, 10)


@pytest.mark.parametrize('offset,count', [(-1, 10), (11, 10), (0, 21)])
def test_manifest_slice_is_bounded(tmp_path, offset, count):
    with pytest.raises(ValueError, match='slice'):
        matrix.manifest_selections(tmp_path, {'kind': 'validation20-v1'}, offset, count)


def test_manifest_plan_never_executes_and_uses_only_extension(tmp_path, monkeypatch, capsys):
    _, manifest = fixture_manifest(monkeypatch)
    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps(manifest))
    monkeypatch.setattr(matrix.subprocess, 'Popen', lambda *a, **kw: pytest.fail('Plan launched process'))
    assert matrix.main(['--root', str(tmp_path), '--output', str(tmp_path / 'output'), '--proofs', str(tmp_path),
                        '--image', 'fixture', '--task-manifest', str(path), '--task-offset', '10',
                        '--tasks-per-benchmark', '10']) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan['attempts'] == 60 and plan['task_offset'] == 10
    assert plan['task_manifest_sha256']
    assert not (tmp_path / 'output').exists()


def test_seeded_twenty_preserve_original_ten():
    tasks = [SimpleNamespace(id=f'{c}-{i}', category=c) for c in ('a','b','c') for i in range(20)]
    sample = lambda n: matrix.balanced_sample(tasks, n, lambda t: t.category, 42)
    assert [t.id for t in sample(20)[:10]] == [t.id for t in sample(10)]


def test_timeout_zero_policy_does_not_fill_other_unknowns():
    from scripts.studies.matched_matrix_report import timeout_zero
    row = dict(benchmark='hybriddeepresearch', backend=matrix.BACKENDS[0], score=None,
               seconds=1800, total_usd_offpeak=None, status='timed_out', model_requests=1,
               native_audit_passed=False)
    original = dict(rows=[row, dict(row, status='native_condition_unverified')], limitations=[])
    revised = timeout_zero(original)
    assert revised['rows'][0]['score'] == 0
    assert revised['rows'][1]['score'] is None
    assert original['rows'][0]['score'] is None


def test_reporting_retains_unknowns_and_does_not_pool_score_metrics():
    from scripts.studies.matched_matrix_report import price, summarize
    assert price(None) is None and price({'input_tokens': 100}) is None
    assert price({'input_tokens': 100, 'cache_read_input_tokens': 1000, 'output_tokens': 10}) == pytest.approx(.000024)
    row = dict(benchmark='dataclawbench', backend=matrix.BACKENDS[0], score=None, seconds=60,
               total_usd_offpeak=None, status='failed', model_requests=1, native_audit_passed=False)
    groups = summarize([row])
    group = next(g for g in groups if g['benchmark'] == 'dataclawbench' and g['backend'] == matrix.BACKENDS[0])
    assert group['attempts'] == 1 and group['graded'] == 0
    assert group['total_usd_offpeak'] is None and group['mean_score'] is None
    row['score'] = 1
    assert all(g['mean_score'] is None for g in summarize([row]) if g['benchmark'] == 'all')


def protocol_fixture(tmp_path, monkeypatch):
    _, manifest = fixture_manifest(monkeypatch)
    # The old baseline remains unchanged; only this explicitly named rerun differs.
    manifest['baseline_settings'] = {'historical': True}
    manifest_path = tmp_path / 'manifest.json'
    manifest_path.write_text(json.dumps(manifest))
    args = ['--root', str(tmp_path), '--output', str(tmp_path / 'output'), '--proofs', str(tmp_path),
            '--image', 'fixture', '--task-manifest', str(manifest_path), '--tasks-per-benchmark', '20']
    settings = matrix.protocol_settings(SimpleNamespace(effort='max', concurrency=8, judge_concurrency=2))
    protocol = tmp_path / 'protocol.json'
    protocol.write_text(json.dumps(settings))
    return args, settings, protocol, manifest_path


def test_explicit_protocol_plan_binds_settings_without_replacing_frozen_tasks(tmp_path, monkeypatch, capsys):
    args, settings, protocol, manifest = protocol_fixture(tmp_path, monkeypatch)
    original = manifest.read_bytes()
    monkeypatch.setattr(matrix.subprocess, 'Popen', lambda *a, **kw: pytest.fail('Plan launched process'))
    monkeypatch.setattr(matrix.runtime, 'credential', lambda *a: pytest.fail('Plan loaded credentials'))
    assert matrix.main(args + ['--protocol-settings', str(protocol)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['attempts'] == 120
    assert result['protocol_settings'] == settings
    assert result['protocol_settings_source'] == 'explicit-protocol'
    assert result['protocol_settings_sha256'] == matrix.digest(protocol)
    assert manifest.read_bytes() == original
    assert not (tmp_path / 'output').exists()


@pytest.mark.parametrize('change', ['effort', 'organization_sha256', 'timeout_seconds_by_benchmark',
                                    'solver_concurrency', 'judge_concurrency', 'extra'])
@pytest.mark.parametrize('execute', [False, True])
def test_explicit_protocol_mismatch_fails_before_dispatch(tmp_path, monkeypatch, change, execute):
    args, settings, protocol, _ = protocol_fixture(tmp_path, monkeypatch)
    settings[change] = 'mismatch'
    protocol.write_text(json.dumps(settings))
    monkeypatch.setattr(matrix.subprocess, 'Popen', lambda *a, **kw: pytest.fail('Invalid protocol launched process'))
    with pytest.raises(ValueError, match='explicit protocol'):
        matrix.main(args + ['--protocol-settings', str(protocol)] + (['--execute'] if execute else []))
    assert not (tmp_path / 'output').exists()


@pytest.mark.parametrize('unsupported', ['no-manifest', 'organization-override'])
def test_explicit_protocol_requires_frozen_tasks_and_default_prompt(tmp_path, monkeypatch, unsupported):
    args, _, protocol, _ = protocol_fixture(tmp_path, monkeypatch)
    if unsupported == 'no-manifest':
        index = args.index('--task-manifest')
        del args[index:index + 2]
    else:
        args += ['--organization-prompt', str(tmp_path / 'override.txt')]
    with pytest.raises(ValueError, match='require a frozen task manifest'):
        matrix.main(args + ['--protocol-settings', str(protocol)])


def test_generic_report_exports_unknowns_and_keeps_failure_denominators(tmp_path):
    from scripts.studies.matched_matrix_report import summarize, write_report
    row = dict(benchmark='dataclawbench', task_id='public-id', backend=matrix.BACKENDS[0],
               status='failed', score=None, seconds=60, total_usd_offpeak=None,
               model_requests=1, native_audit_passed=False, grade_status='unknown')
    report = dict(run='fixture', authorization=dict(effort='high', solver_concurrency=6, judge_concurrency=2,
                  protocol_settings_source='explicit-protocol', protocol_settings_sha256='abc'),
                  rows=[row], groups=summarize([row]), limitations=['Missing accounting is unknown.'])
    output = tmp_path / 'report'
    write_report(report, output)
    assert json.loads((output / 'summary.json').read_text())['rows'][0]['score'] is None
    assert '0/1 | unknown' in (output / 'REPORT.md').read_text()
    assert 'explicit-protocol' in (output / 'REPORT.md').read_text()
    assert 'public-id' in (output / 'task-results.csv').read_text()
    with pytest.raises(FileExistsError):
        write_report(report, output)
