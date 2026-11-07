import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.common import grading
from scripts.studies import benchmark_matrix
from common.io import read_json
from scripts.studies.matched_matrix_report import read


def invoke(tmp_path, benchmark, *, enabled, category=None, answer='fixture answer', code=0):
    run = tmp_path / 'run'
    run.mkdir()
    (run / 'predictions.jsonl').write_text(json.dumps(dict(final_answer=answer)) + '\n')
    task = SimpleNamespace(id='fixture', category=category)
    commands = []
    def command_run(command, log):
        commands.append(command)
        target = Path(command[command.index('--output') + 1])
        target.mkdir(parents=True)
        calls = int(command[command.index('--judge-limit') + 1]) if '--judge-limit' in command else 0
        (target / 'receipt.json').write_text(json.dumps(dict(judge_calls=calls)))
        return code
    result = grading.grade_attempt(benchmark, task, 'claude-code-subagents', run,
        data_root=tmp_path/'data', grades_root=tmp_path/'grades', credentials=tmp_path/'unused.env',
        judge_enabled=enabled, key=None, command_run=command_run, log=tmp_path/'grade')
    return result, commands


def test_matrix_uses_the_shared_grader():
    assert benchmark_matrix.grade_attempt is grading.grade_attempt


def test_shared_json_reader_keeps_missing_defaults_but_does_not_hide_corruption(tmp_path):
    assert read is read_json
    path = tmp_path / 'receipt.json'
    assert read(path, {}) == {}
    path.write_text('{"value": 3}')
    assert read(path) == {'value': 3}
    path.write_text('invalid json')
    with pytest.raises(json.JSONDecodeError):
        read(path, {})


@pytest.mark.parametrize('benchmark,category', [
    ('dataclawbench', None), ('hybriddeepresearch', 'sql_to_search'),
    ('hybriddeepresearch', 'search_to_sql')])
@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('answer', ['', 'fixture answer'])
def test_grading_preserves_sql_and_paid_judge_scope(tmp_path, benchmark, category, enabled, answer):
    result, commands = invoke(tmp_path, benchmark, enabled=enabled, category=category, answer=answer)
    command, = commands
    expected_calls = int(enabled and bool(answer) and category != 'search_to_sql')
    assert result['status'] == 'completed' and result['judge_calls'] == expected_calls
    assert command[1:3] == ['-m', 'scripts.' + benchmark + '.score']
    assert ('--execute-sql' in command) is (category == 'search_to_sql')
    assert ('--execute-judges' in command) is bool(expected_calls)
    if expected_calls:
        assert command[command.index('--judge-limit')+1] == '1'
        assert command[command.index('--judge-model')+1] == 'deepseek-flash'
    assert '--execute' not in command


@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('status', ['cli_exited', 'native_condition_unverified'])
@pytest.mark.parametrize('grade_status', ['pending_judge', 'graded'])
def test_krama_reuses_numeric_grade_and_only_judges_authorized_completed_attempts(
        tmp_path, monkeypatch, enabled, status, grade_status):
    grade = dict(status=grade_status, score=None if grade_status == 'pending_judge' else 1)
    (tmp_path/'summary.json').write_text(json.dumps(dict(rows=[dict(
        status=status, grade=grade, pipeline_exit_code=0, pipeline_answer_matches_submission=True)])))
    calls = []
    def judge(**kwargs):
        calls.append(kwargs)
        return dict(status='graded', grade=dict(status='graded', score=1), attempted_calls=1)
    monkeypatch.setattr(grading, 'judge_once', judge)
    result = grading.grade_attempt('kramabench', SimpleNamespace(id='fixture', query='public fixture'),
        'claude-code-subagents', tmp_path, data_root=tmp_path, grades_root=tmp_path/'grades',
        credentials=tmp_path/'unused.env', judge_enabled=enabled, key='fake',
        command_run=lambda *a: pytest.fail('Krama must not launch an external scorer'), log=tmp_path/'log')
    expected = int(enabled and grade_status == 'pending_judge')
    assert len(calls) == result['judge_calls'] == expected
    assert result['pipeline_exit_code'] == 0
    assert result['pipeline_answer_matches_submission'] is True
    assert result['grade'] == (dict(status='graded', score=1) if expected else grade)


@pytest.mark.parametrize('benchmark', ['dataclawbench', 'hybriddeepresearch', 'kramabench'])
def test_missing_artifact_never_dispatches_a_judge(tmp_path, monkeypatch, benchmark):
    monkeypatch.setattr(grading, 'judge_once', lambda **kw: pytest.fail('Missing artifact invoked judge'))
    result = grading.grade_attempt(benchmark, SimpleNamespace(id='fixture'), 'claude-code-subagents',
        tmp_path, data_root=tmp_path, grades_root=tmp_path/'grades', credentials=tmp_path/'unused.env',
        judge_enabled=True, key='fake', command_run=lambda *a: pytest.fail('Missing artifact launched scorer'),
        log=tmp_path/'log')
    assert result['status'] == ('missing_summary' if benchmark == 'kramabench' else 'missing_predictions')
    assert result['judge_calls'] == 0


def test_failed_external_grade_is_not_retried(tmp_path):
    result, commands = invoke(tmp_path, 'dataclawbench', enabled=True, code=7)
    assert len(commands) == 1
    assert result['status'] == 'grading_failed' and result['returncode'] == 7


def test_krama_fatal_judge_error_reaches_batch_controller(tmp_path, monkeypatch):
    (tmp_path/'summary.json').write_text(json.dumps(dict(rows=[dict(status='cli_exited',
        grade=dict(status='pending_judge', score=None))])))
    monkeypatch.setattr(grading, 'judge_once', lambda **kw: dict(status='judge_error', fatal=True,
        attempted_calls=1))
    result = grading.grade_attempt('kramabench', SimpleNamespace(id='fixture', query='public'),
        'claude-code-subagents', tmp_path, data_root=tmp_path, grades_root=tmp_path/'grades',
        credentials=tmp_path/'unused', judge_enabled=True, key='synthetic', command_run=None, log=None)
    assert result['fatal_provider_error'] is True and result['judge_calls'] == 1


def test_external_fatal_judge_error_is_redacted_and_stops_queue(tmp_path):
    from scripts.common.score import judge_rows
    class Failure(Exception):
        status_code = 401
    def create(**kwargs):
        raise Failure('synthetic-private-key')
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    rows = [dict(task_id=str(i), task_prompt='public fixture', response='candidate', answer='reference')
            for i in range(2)]
    results = judge_rows(rows, benchmark='dataclawbench', upstream=tmp_path, model='fixture',
                         output=tmp_path, client=client)
    assert results[0]['fatal_provider_error'] is True and results[0]['http_status'] == 401
    assert results[1]['status'] == 'not_started'
    assert 'synthetic-private-key' not in json.dumps(results)
