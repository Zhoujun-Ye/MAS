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


def test_report_merge_requires_complete_disjoint_slices():
    from scripts.studies.validation20_report import merge_rows
    manifest = dict(benchmarks={b: [dict(task_id=f'{b}-{i}') for i in range(20)] for b in matrix.BENCHMARKS})
    batches = [dict(run=f'batch-{n}', rows=[dict(benchmark=b, task_id=f'{b}-{i}', backend=k)
               for b in matrix.BENCHMARKS for i in range(n * 10, (n + 1) * 10) for k in matrix.BACKENDS]) for n in range(2)]
    assert len(merge_rows(manifest, batches)) == 120
    batches[1]['rows'][-1] = batches[1]['rows'][0]
    with pytest.raises(ValueError, match='exactly cover'):
        merge_rows(manifest, batches)


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
