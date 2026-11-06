import json
from types import SimpleNamespace

import pytest

from scripts.studies import benchmark_matrix as matrix
from scripts.server import smoke
from scripts.studies import run_validation20_native as study


def cli_args(tmp_path, *extra):
    return ['--root', str(tmp_path), '--output', str(tmp_path / 'output'),
            '--proofs', str(tmp_path), '--image', 'fixture', *extra]


def test_native_study_is_plan_only_by_default(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(study.benchmark_matrix, 'main', lambda *a: pytest.fail('Plan dispatched matrix'))
    assert study.main(['--output', str(tmp_path / 'output'), '--proofs', str(tmp_path)]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan['attempts'] == 60 and plan['maximum_judge_calls'] == 53
    assert plan['paid_calls_authorized'] is False and plan['retries'] == 0
    assert not (tmp_path / 'output').exists()
    assert not list(tmp_path.glob('*.txt'))


def test_single_condition_rejects_two_condition_authorization(tmp_path, monkeypatch):
    tasks = [(b, SimpleNamespace(id=f'task-{i}', category='test'))
             for b in matrix.BENCHMARKS for i in range(2)]
    monkeypatch.setattr(matrix, 'selections', lambda root: tasks)
    with pytest.raises(ValueError, match='6 authorized solvers'):
        matrix.main(cli_args(tmp_path, '--backends', 'claude-code-subagents', '--execute',
                             '--authorized-attempts', '12', '--authorized-judges', '0'))
    assert not (tmp_path / 'output').exists()


def test_native_study_plan_resolves_config_without_relying_on_cwd(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert study.main(['--output', str(tmp_path / 'output'), '--proofs', str(tmp_path)]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan['task_manifest_sha256'] == 'fc39ad8539e2af0b140a6b9a8b3144d241742b2c3b2424b6d74ae03f1829e0a5'
    with pytest.raises(ValueError, match='source root'):
        study.main(['--output', str(tmp_path / 'output'), '--proofs', str(tmp_path), '--execute'])
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('extra', [
    ['--backends', 'claude-code-subagents', 'claude-code-subagents'],
    ['--backends', 'claude-code-single-agent', '--organization-prompt', 'unused.txt'],
])
def test_invalid_condition_selection_is_rejected(tmp_path, extra):
    with pytest.raises(ValueError):
        matrix.main(cli_args(tmp_path, *extra))
    assert not (tmp_path / 'output').exists()


def test_provisioning_smoke_keeps_four_attempt_plan_without_paid_calls(tmp_path, monkeypatch, capsys):
    dc = SimpleNamespace(id='dc', benchmark='dataclawbench', web=False)
    hdr = SimpleNamespace(id='hdr', benchmark='hybriddeepresearch', category='search_to_sql', web=True)
    monkeypatch.setattr(smoke, 'dc_tasks', lambda _: [dc])
    monkeypatch.setattr(smoke, 'hdr_tasks', lambda _: [hdr])
    monkeypatch.setattr(smoke.runtime, 'credential', lambda *a: pytest.fail('Plan loaded credentials'))
    monkeypatch.setattr('sys.argv', ['smoke', '--root', str(tmp_path), '--output', str(tmp_path/'out'),
        '--proofs', str(tmp_path), '--image', 'fixture', '--credentials', 'unused.env',
        '--authorized-attempts', '4', '--budget-cny', '10'])
    smoke.main()
    result = json.loads(capsys.readouterr().out)
    assert result['attempts'] == len(result['selections']) == 4
    assert {r['backend'] for r in result['selections']} == set(matrix.BACKENDS)
    assert not (tmp_path/'out').exists()
