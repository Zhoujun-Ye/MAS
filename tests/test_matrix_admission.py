import json
from types import SimpleNamespace

import pytest

from scripts.studies import benchmark_matrix as matrix


def test_sql_evaluator_preflight_uses_current_python_without_scoring(tmp_path, monkeypatch):
    calls=[]
    monkeypatch.setattr(matrix.subprocess, 'run', lambda command, **kw: calls.append((command, kw)))
    result=matrix.sql_evaluator_preflight(tmp_path)
    command, options=calls[0]
    assert command == [matrix.sys.executable, str(tmp_path/'hybriddeepresearch/upstream/evaluation/s2sql_eval.py'), '--help']
    assert options == dict(check=True, capture_output=True, timeout=30)
    assert result['cli_imports_verified'] and result['paid_calls']==0


@pytest.mark.parametrize('error', [OSError('missing interpreter'),
    matrix.subprocess.CalledProcessError(1, ['fixture']),
    matrix.subprocess.TimeoutExpired(['fixture'], 30)])
def test_sql_evaluator_preflight_fails_closed(tmp_path, monkeypatch, error):
    def fail(*a, **kw):raise error
    monkeypatch.setattr(matrix.subprocess, 'run', fail)
    with pytest.raises(ValueError, match='documented evaluation Python'):
        matrix.runtime_preflight(SimpleNamespace(root=tmp_path, sql_grading_required=True))


@pytest.mark.parametrize('requested,verified', [('max', True), ('high', False), (None, None)])
def test_runtime_preflight_rejects_effort_mismatch(tmp_path, monkeypatch, requested, verified):
    folder = tmp_path / 'claude-code-subagents'
    folder.mkdir()
    (folder / 'proof.json').write_text(json.dumps(dict(requested_effort=requested,
                                                     request_effort_verified=verified)))
    monkeypatch.setattr(matrix.subprocess, 'check_output', lambda *a, **kw: '[{"Id":"image"}]')
    monkeypatch.setattr(matrix, 'digest', lambda *a: 'binary')
    monkeypatch.setattr(matrix, 'validate_runtime', lambda *a, **kw: None)
    args = SimpleNamespace(image='fixture', proofs=tmp_path, backends=['claude-code-subagents'], effort='high')
    with pytest.raises(ValueError, match='request-effort'):
        matrix.runtime_preflight(args)


def test_max_effort_is_also_bound_to_observed_proof(tmp_path, monkeypatch):
    folder = tmp_path / 'claude-code-subagents'
    folder.mkdir()
    (folder / 'proof.json').write_text(json.dumps(dict(requested_effort='high', request_effort_verified=True)))
    monkeypatch.setattr(matrix.subprocess, 'check_output', lambda *a, **kw: '[{"Id":"image"}]')
    monkeypatch.setattr(matrix, 'digest', lambda *a: 'binary')
    monkeypatch.setattr(matrix, 'validate_runtime', lambda *a, **kw: None)
    with pytest.raises(ValueError, match='request-effort'):
        matrix.runtime_preflight(SimpleNamespace(image='fixture', proofs=tmp_path,
            backends=['claude-code-subagents'], effort='max'))


def args(tmp_path, *extra):
    return ['--root', str(tmp_path), '--output', str(tmp_path/'out'), '--proofs', str(tmp_path),
        '--image', 'fixture', '--benchmarks', 'kramabench', '--conditions', 'claude-code-subagents',
        '--concurrency', '1', '--judge-concurrency', '1', '--estimated-cost','10', *extra]


def fixture_tasks(monkeypatch):
    monkeypatch.setattr(matrix, 'selections', lambda *a: [
        ('kramabench', SimpleNamespace(id=f'fixture-{i}')) for i in range(2)])


@pytest.mark.parametrize('mode', ['--check-runtime', '--execute'])
def test_failed_admission_never_creates_run_or_reads_credentials(tmp_path, monkeypatch, mode):
    fixture_tasks(monkeypatch)
    def reject(*a):
        raise ValueError('fixture mismatched proof')
    monkeypatch.setattr(matrix, 'runtime_preflight', reject)
    monkeypatch.setattr(matrix.runtime, 'credential', lambda *a: pytest.fail('Must not read credentials'))
    monkeypatch.setattr(matrix.subprocess, 'Popen', lambda *a, **kw: pytest.fail('Must not launch'))
    with pytest.raises(ValueError, match='mismatched proof'):
        matrix.main(args(tmp_path, mode, '--authorized-attempts', '2'))
    assert not (tmp_path/'out').exists()


def test_runtime_check_plan_reports_readiness_without_execution(tmp_path, monkeypatch, capsys):
    fixture_tasks(monkeypatch)
    monkeypatch.setattr(matrix, 'runtime_preflight', lambda *a: dict(image_id='image', paid_calls=0))
    monkeypatch.setattr(matrix.subprocess, 'Popen', lambda *a, **kw: pytest.fail('Plan must not launch'))
    assert matrix.main(args(tmp_path, '--check-runtime')) == 0
    assert json.loads(capsys.readouterr().out)['runtime_preflight']['paid_calls'] == 0
    assert not (tmp_path/'out').exists()


def test_task_preflight_failure_prevents_all_paid_dispatch(tmp_path, monkeypatch):
    fixture_tasks(monkeypatch)
    monkeypatch.setattr(matrix, 'runtime_preflight', lambda *a: dict(image_id='image'))
    monkeypatch.setattr(matrix.runtime, 'credential', lambda *a: pytest.fail('No paid admission'))
    class Process:
        def __init__(self, command, **kw):
            assert '--execute' not in command
        def wait(self, **kw):
            return 1
    monkeypatch.setattr(matrix.subprocess, 'Popen', Process)
    with pytest.raises(RuntimeError, match='no paid attempts'):
        matrix.main(args(tmp_path, '--execute', '--authorized-attempts', '2'))
    assert json.loads((tmp_path/'out/failure.json').read_text())['balance_preflight_passed'] is False


def test_fatal_judge_stops_queued_grading(tmp_path, monkeypatch):
    from pathlib import Path
    fixture_tasks(monkeypatch)
    monkeypatch.setattr(matrix, 'runtime_preflight', lambda *a: dict(image_id='image'))
    monkeypatch.setattr(matrix.runtime, 'credential', lambda *a: 'synthetic')
    monkeypatch.setattr(matrix.runtime, 'safe_balance', lambda *a: dict(response=dict(is_available=True,
        balance_infos=[dict(currency='CNY', total_balance='100')])))
    class Process:
        def __init__(self, command, **kw):
            if '--execute' in command:
                out = Path(command[command.index('--output')+1])
                task = command[command.index('--task-id')+1]
                folder = out / task / 'claude-code-subagents'
                folder.mkdir(parents=True)
                (folder/'report.json').write_text('{"status":"cli_exited"}')
        def wait(self, **kw):
            return 0
    monkeypatch.setattr(matrix.subprocess, 'Popen', Process)
    graded = []
    monkeypatch.setattr(matrix,'needs_judge',lambda *a:True)
    def grade(b, t, k, *a, **kw):
        graded.append(t.id)
        return dict(benchmark=b, task_id=t.id, backend=k, status='judge_error',
                    judge_calls=1, fatal_provider_error=True)
    monkeypatch.setattr(matrix, 'grade_attempt', grade)
    assert matrix.main(args(tmp_path, '--execute', '--authorized-attempts', '2', '--authorized-judges', '2')) == 1
    assert len(graded) == 1
    summary = json.loads((tmp_path/'out/summary.json').read_text())
    assert summary['interrupted'] is True
    assert sorted(g['status'] for g in summary['grades']) == ['judge_error', 'not_started']
