import threading
import json

import pytest

from harness.comparison import selected_conditions
from harness.llm import ChatClient, ModelConfig, ProviderError
from scripts.kramabench.batch import guarded_client


def test_all_conditions_are_explicit_and_do_not_change_existing_sizes():
    assert list(selected_conditions('all')) == ['single', 'team_coordinator', 'team_full']
    assert len(selected_conditions('both')) == 2
    assert len(selected_conditions('team')) == 1
    with pytest.raises(ValueError):
        selected_conditions('all', 'full')


def test_fatal_provider_error_stops_other_question_clients(monkeypatch):
    stop = threading.Event()
    calls = []
    def post(self, body, *, timeout=None):
        calls.append(body)
        raise ProviderError('http_402', 'fixture balance failure', 402)
    monkeypatch.setattr(ChatClient, '_post', post)
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'offline-test')
    factory = guarded_client(stop)
    first, second = factory(ModelConfig(model='offline')), factory(ModelConfig(model='offline'))
    try:
        with pytest.raises(ProviderError, match='http_402'):
            first._post({})
        assert stop.is_set()
        with pytest.raises(ProviderError, match='batch_stopped'):
            second._post({})
        assert calls == [{}]
    finally:
        first._http.close()
        second._http.close()


@pytest.mark.parametrize('interrupted', [False, True])
def test_batch_records_launcher_error_or_interruption(tmp_path, monkeypatch, interrupted):
    from benchmarks.kramabench.tasks import Task
    from scripts.kramabench import batch
    monkeypatch.setattr(batch, 'load_tasks', lambda path: ([Task('fixture', 'legal', 'public')], {}))
    monkeypatch.setattr(batch, 'scoring_contract', lambda path: {'fixture': True})
    (tmp_path / 'data/legal/input').mkdir(parents=True)
    monkeypatch.setattr(batch, 'source_digest', lambda: 'fixture-source')
    def fail(*args, **kwargs):
        raise ValueError('fixture launcher failure')
    monkeypatch.setattr(batch.pilot, 'main', fail)
    root = tmp_path / 'batch'
    monkeypatch.setattr(batch.sys, 'argv', ['batch', '--upstream', str(tmp_path), '--image', 'fixture',
        '--output', str(root), '--task-ids', 'fixture', '--execute-paid'])
    if interrupted:
        def interrupt(*args, **kwargs):
            raise KeyboardInterrupt
        monkeypatch.setattr(batch, 'bounded_jobs', interrupt)
        with pytest.raises(KeyboardInterrupt):
            batch.main()
    else:
        batch.main()
    receipt = json.loads((root / 'batch.json').read_text())
    assert receipt['model_calls_per_attempt'] == 600
    assert receipt['tool_calls_per_attempt'] == 300
    assert receipt['status'] == ('interrupted' if interrupted else 'finished_with_errors')
    assert receipt['results']['fixture']['status'] == ('not_run_after_interruption' if interrupted else 'launcher_error')


def test_full_dry_run_selects_pinned_tasks_without_dispatch_or_credentials(tmp_path, monkeypatch):
    from benchmarks.kramabench.tasks import Task
    from scripts.kramabench import batch
    tasks = [Task('fixture-a', 'legal', 'public'), Task('fixture-b', 'legal', 'public')]
    monkeypatch.setattr(batch, 'load_tasks', lambda path: (tasks, {}))
    monkeypatch.setattr(batch, 'scoring_contract', lambda path: {'fixture': True})
    monkeypatch.setattr(batch, 'source_digest', lambda: 'fixture-source')
    def forbidden(*args, **kwargs):
        raise AssertionError('Dry-run must not dispatch paid work')
    monkeypatch.setattr(batch, 'bounded_jobs', forbidden)
    monkeypatch.setattr(batch.pilot, 'main', forbidden)
    (tmp_path / 'data/legal/input').mkdir(parents=True)
    root = tmp_path / 'plan'
    monkeypatch.setattr(batch.sys, 'argv', ['batch', '--upstream', str(tmp_path), '--image', 'fixture',
        '--output', str(root), '--all-tasks', '--concurrency', '12', '--dry-run'])
    result = batch.main()
    assert result['status'] == 'preflight_only' and result['planned_attempts'] == 6
    assert result['authorized_attempts'] == 0
    assert result['task_ids'] == [t.id for t in tasks]
    assert result['resource_plan']['active_questions'] == 2
    assert result['thread_limits']['OPENBLAS_NUM_THREADS'] == '1'
    assert result['limits']['session_model_calls'] == 600


def test_explicit_judging_runs_after_solver_window_drains(tmp_path, monkeypatch):
    from benchmarks.kramabench.tasks import Task
    from scripts.kramabench import batch
    monkeypatch.setattr(batch, 'load_tasks', lambda path: ([Task('fixture', 'legal', 'public')], {}))
    monkeypatch.setattr(batch, 'scoring_contract', lambda path: {'fixture': True})
    monkeypatch.setattr(batch, 'source_digest', lambda: 'source')
    (tmp_path / 'data/legal/input').mkdir(parents=True)
    order = []
    def solve(*args, **kwargs):
        order.append('solvers_done')
        return {'status': 'attempts_finished'}
    def judge(root, *args, **kwargs):
        assert order == ['solvers_done']
        assert json.loads((root / 'batch.json').read_text())['status'] == 'judging'
        order.append('judge')
        return {'attempted_calls': 1, 'status': 'completed'}
    monkeypatch.setattr(batch.pilot, 'main', solve)
    monkeypatch.setattr(batch, 'adjudicate', judge)
    root = tmp_path / 'batch'
    monkeypatch.setattr(batch.sys, 'argv', ['batch', '--upstream', str(tmp_path), '--image', 'fixture',
        '--output', str(root), '--task-ids', 'fixture', '--execute-paid', '--judge-model', 'deepseek-flash'])
    batch.main()
    receipt = json.loads((root / 'batch.json').read_text())
    assert receipt['paid_judge_calls'] == 1 and receipt['judge_status'] == 'completed'
    assert receipt['status'] == 'attempts_finished' and order == ['solvers_done', 'judge']
