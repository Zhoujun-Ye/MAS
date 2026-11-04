import json

import pytest

from scripts.studies import grade_interrupted_matrix as recovery


def fixture_run(tmp_path, status='cli_exited'):
    selection = dict(benchmark='dataclawbench', task_id='fixture', backend='claude-code-single-agent')
    authorization = dict(selections=[selection], maximum_judge_calls=1, authorized_judges=1)
    (tmp_path / 'authorization.json').write_text(json.dumps(authorization))
    folder = tmp_path / 'solvers/dataclawbench/fixture/claude-code-single-agent/fixture/claude-code-single-agent'
    folder.mkdir(parents=True)
    (folder / 'report.json').write_text(json.dumps(dict(status=status, cli=dict(returncode=0))))
    return authorization


def test_recovery_plan_is_read_only_and_never_launches(tmp_path, monkeypatch, capsys):
    fixture_run(tmp_path)
    monkeypatch.setattr(recovery.runtime, 'credential', lambda *a: pytest.fail('Plan read credentials'))
    monkeypatch.setattr(recovery.subprocess, 'run', lambda *a, **kw: pytest.fail('Plan launched process'))
    assert recovery.main(['--run', str(tmp_path), '--root', str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)['new_solver_calls'] == 0
    assert not (tmp_path / 'grading-recovery').exists()


def test_recovery_rejects_live_or_missing_attempts(tmp_path):
    authorization = fixture_run(tmp_path, 'running')
    with pytest.raises(ValueError, match='not terminal'):
        recovery.retained_rows(tmp_path, authorization)
    next(tmp_path.glob('solvers/**/report.json')).unlink()
    with pytest.raises(ValueError, match='Missing retained attempt'):
        recovery.retained_rows(tmp_path, authorization)


def test_recovery_refuses_repeated_grading(tmp_path):
    fixture_run(tmp_path)
    (tmp_path / 'grades').mkdir()
    with pytest.raises(ValueError, match='repeat grading'):
        recovery.main(['--run', str(tmp_path), '--root', str(tmp_path), '--execute', '--authorized-judges', '1'])
