"""Free regression tests for the three follow-up review findings."""

import json
import threading
from types import SimpleNamespace

import pytest

from scripts.common import run as external
from scripts.kramabench import run as krama
from scripts.kramabench import cli_runtime
from harness.runtime_support.resources import ContainerResources


@pytest.mark.parametrize('field', ['subagent_starts', 'executed_delegation_tools',
    'exposed_delegation_tools', 'member_transcript_files', 'native_team_configs',
    'teammate_idle_events', 'accounting', None])
@pytest.mark.parametrize('status', ['cli_exited', 'timed_out', 'cli_error'])
def test_external_single_violation_is_not_a_missing_evidence_grade(tmp_path, monkeypatch, field, status):
    work = tmp_path/'workspace'
    work.mkdir()
    (work/'submission.json').write_text('{"final_answer":"synthetic"}')
    audit = dict(passed=False, session_end=False)
    if field and field != 'accounting':
        audit[field] = 1
    accounting = dict(observed_messages=1)
    if field == 'accounting':
        accounting['by_role'] = dict(member=dict(observed_messages=1))
    monkeypatch.setattr(external, 'inspect_run', lambda *a: {})
    monkeypatch.setattr(external, 'native_surface', lambda *a: {})
    monkeypatch.setattr(external, 'native_single_agent', lambda *a: audit)
    monkeypatch.setattr(external.subprocess, 'run', lambda *a, **kw:
        SimpleNamespace(returncode=0, stdout=json.dumps(accounting)))
    result = external.finalize_attempt(tmp_path, SimpleNamespace(backend='claude-code-single-agent'),
        dict(status=status, cli=dict(status=status, returncode=0)))
    expected = status if status != 'cli_exited' else (
        'single_agent_condition_violated' if field else 'native_condition_unverified')
    assert result['status'] == expected
    assert bool(result.get('final_answer')) is (field is None and status == 'cli_exited')
    if field:
        assert result['condition_status'] == 'single_agent_condition_violated'


@pytest.mark.parametrize('status,eligible', [('cli_exited', True), ('native_condition_unverified', True),
    ('cli_error', False), ('timed_out', False), ('single_agent_condition_violated', False),
    ('single_agent_evidence_unverified', False), ('launcher_error', False)])
def test_standalone_krama_uses_same_judge_admission_as_matrix(tmp_path, monkeypatch, status, eligible):
    from scripts.common.grading import needs_judge
    backend = 'claude-code-single-agent'
    task = SimpleNamespace(id='fixture', query='synthetic')
    report = dict(task_id=task.id, backend=backend, status=status)
    collected = dict(report, grade=dict(status='pending_judge', score=None))
    (tmp_path/'summary.json').write_text(json.dumps(dict(rows=[collected])))
    assert needs_judge('kramabench', task, tmp_path, True) is eligible
    monkeypatch.setattr(krama.shared, 'credential', lambda *a: 'synthetic')
    balance = dict(response=dict(is_available=True, balance_infos=[dict(currency='CNY', total_balance='100')]))
    monkeypatch.setattr(krama, 'safe_balance', lambda *a: balance)
    monkeypatch.setattr(krama, 'monitor', lambda o,s,a,l,d: d.wait())
    monkeypatch.setattr(krama.signal, 'signal', lambda *a: None)
    monkeypatch.setattr(krama.runtime, 'run_attempt', lambda *a: report)
    monkeypatch.setattr(krama, 'admission', lambda *a: dict(passed=False))
    monkeypatch.setattr(krama.runtime, 'collect_attempt', lambda *a: collected)
    calls = []
    def judge(**kwargs):
        calls.append(kwargs)
        return dict(status='graded', grade=dict(score=1), attempted_calls=1)
    monkeypatch.setattr(krama, 'judge_once', judge)
    args = SimpleNamespace(output=tmp_path, credentials=tmp_path/'unused', backends=[backend],
        concurrency=1, judge_limit=1, upstream=tmp_path)
    krama.execute(args, [task], dict(admission_task=task.id))
    assert len(calls) == int(eligible)


@pytest.mark.parametrize('status', ['timed_out', 'cli_error', 'interrupt'])
@pytest.mark.parametrize('backend', ['claude-code-single-agent', 'claude-code-subagents'])
@pytest.mark.parametrize('runner', ['krama', 'external'])
def test_recorded_failure_stops_before_sampler_close(tmp_path, monkeypatch, status, backend, runner):
    from benchmarks.kramabench.tasks import Task
    state = []
    class Gateway:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
    class Resources:
        def __init__(self, *a): pass
        def start(self): return self
        def close(self, **kwargs):
            assert 'stopped' in state
            assert kwargs.get('final_sample') is False
            state.append('sampler-closed')
            return {}
        def record_exit(self): return {}
    class Adapter:
        def __init__(self, *a): pass
        def run(self, *a, **kw):
            if status == 'interrupt': raise KeyboardInterrupt
            return dict(status=status)
    def stop(identity):
        state.append('stopped')
        return dict(stopped=True)
    monkeypatch.setattr(cli_runtime, 'CredentialGateway', Gateway)
    monkeypatch.setattr(cli_runtime, 'ContainerResources', Resources)
    monkeypatch.setattr(cli_runtime, 'ClaudeCodeSingleAgentCLI', Adapter)
    monkeypatch.setattr(cli_runtime, 'ClaudeCodeSubagentsCLI', Adapter)
    monkeypatch.setattr(cli_runtime, 'container', lambda *a, **kw: 'synthetic')
    monkeypatch.setattr(cli_runtime, 'stop_container', stop)
    monkeypatch.setattr(cli_runtime.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=0, stdout='{}'))
    args = SimpleNamespace(output=tmp_path, upstream=tmp_path, image='fixture', timeout=1,
                           record_resources=True, cpus=8, backend=backend, data=tmp_path,
                           web_search=None, max_web_requests=None)
    if runner == 'external':
        from harness.runtime_support import resources
        monkeypatch.setattr(resources, 'ContainerResources', Resources)
        monkeypatch.setattr(external, 'CredentialGateway', Gateway)
        monkeypatch.setattr(external, 'mounts', lambda *a: [])
        monkeypatch.setattr(external, 'instructions', lambda *a, **kw: 'synthetic')
        monkeypatch.setitem(external.BACKENDS, backend, Adapter)
        monkeypatch.setattr(external.runtime, 'container', lambda *a, **kw: 'synthetic')
        monkeypatch.setattr(external.runtime, 'stop_container', stop)
    def execute():
        if runner == 'external':
            task = SimpleNamespace(id='fixture', benchmark='dataclawbench', question='synthetic', web=False)
            return external.attempt(task, args, 'synthetic')
        return cli_runtime.run_attempt(Task('fixture', 'astronomy', 'synthetic'), backend, args,
            'synthetic', threading.Event(), set(), threading.Lock())
    if status == 'interrupt':
        with pytest.raises(KeyboardInterrupt): execute()
    else:
        assert execute()['status'] == status
    assert state[0] == 'stopped'


def test_stopped_sampler_keeps_partial_metrics_without_reading_destroyed_cgroup(tmp_path, monkeypatch):
    collector = ContainerResources('fixture', tmp_path, 8)
    monkeypatch.setattr(collector, 'sample', lambda: pytest.fail('Stopped cgroup must not be sampled'))
    result = collector.close(final_sample=False)
    assert result['capture_complete'] is False
    assert result['final_sample_requested'] is False
    assert collector.close() is result


def test_sampler_join_is_bounded_and_marks_incomplete_capture(tmp_path, monkeypatch):
    collector = ContainerResources('fixture', tmp_path, 8)
    joins = []
    collector.thread = SimpleNamespace(join=lambda **kw: joins.append(kw), is_alive=lambda: True)
    monkeypatch.setattr(collector, 'sample', lambda: pytest.fail('No racing final sample'))
    monkeypatch.setattr(collector, 'exit_state', lambda: {})
    result = collector.close()
    assert joins == [dict(timeout=1)]
    assert result['capture_complete'] is False
    assert 'sampler_shutdown_timeout' in result['sample_errors']
