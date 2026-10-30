import json

import pytest

from fakes import ScriptedClient
from test_agent_team import build, submit_or_wait
from harness.agent import Observation
from harness.llm import ProviderError
from harness.trace import read_trace


@pytest.mark.parametrize('scheduler', ['controlled', 'async'])
@pytest.mark.parametrize('kind', ['local_context', 'provider_context', 'output'])
def test_member_overflow_does_not_stop_peer_and_snapshots_once(tmp_path, scheduler, kind):
    captured = []
    def snapshot(role, revision, paths):
        captured.append(role)
        return dict(patch=role)
    def respond(messages, tools, choice):
        role = messages[0]['content'].split('Member identity: ')[1].split('.')[0]
        if role == 'researcher':
            if kind == 'provider_context':
                raise ProviderError('context_length', 'fixture')
            return dict(finish='length', calls=[('stock', {})])
        if role == 'reviewer':
            if not any(m['role'] == 'assistant' for m in messages):
                return dict(calls=[('list_tasks', {})])
            return submit_or_wait(messages)
        return dict(calls=[('wait_for_message', {})])
    task, team, trace = build(tmp_path, 'agent_team', ScriptedClient(respond), scheduler=scheduler,
        max_calls=None, submission_hook=snapshot,
        member_inputs={'researcher': 'x' * 300000} if kind == 'local_context' else {})
    result = team.run_task(task)
    assert result['failure_class'] == 'agent_failure'
    assert result['halted_members'] == {'researcher': 'output_length' if kind == 'output' else 'context_length'}
    assert team.submitted['reviewer'] and team.budgets['researcher'].used == 0
    assert captured.count('researcher') == captured.count('reviewer') == 1
    assert result['evaluation_snapshots']['researcher']['kind'] == 'terminal'
    trace.close()


@pytest.mark.parametrize('scheduler', ['controlled', 'async'])
def test_output_recovery_refuses_truncated_actions_then_continues(tmp_path, scheduler):
    def respond(messages, tools, choice):
        role = messages[0]['content'].split('Member identity: ')[1].split('.')[0]
        if role == 'leader':
            return dict(content='Final')
        if role == 'researcher' and not any(m['role'] == 'assistant' for m in messages):
            return dict(finish='length', calls=[('stock', {})])
        return submit_or_wait(messages)
    task, team, trace = build(tmp_path, 'agent_team', ScriptedClient(respond), scheduler=scheduler)
    result = team.run_task(task)
    assert result['submission_status'] == 'submitted'
    assert not result['halted_members'] and team.budgets['researcher'].used == 0
    assert 'No tools from that reply were executed' in str(team.agents['researcher'].messages)
    trace.close()


def test_submitted_readonly_checks_do_not_reopen_or_enable_writes(tmp_path):
    def respond(messages, tools, choice):
        role = messages[0]['content'].split('Member identity: ')[1].split('.')[0]
        if role == 'leader':
            return dict(content='Final')
        if role == 'researcher':
            return dict(calls=[('submit_assignment', dict(report='Ready', paths=[])), ('stock', {})])
        return submit_or_wait(messages)
    task, team, trace = build(tmp_path, 'agent_team', ScriptedClient(respond))
    team.domain['stock'].read_only = True
    result = team.run_task(task)
    assert result['submission_status'] == 'submitted'
    assert team.budgets['researcher'].used == 1 and team.tasks['researcher']['revision'] == 1
    assert team.evidence
    trace.close()


def test_unchanged_state_is_not_reappended_and_leader_is_not_worker_task(tmp_path):
    task, team, trace = build(tmp_path, 'agent_team', max_calls=None, max_messages=None, max_reads=None)
    team.run_task(task)
    agent = team.agents['researcher']
    team.prepare_call(agent)
    count = sum('"team_state"' in m.get('content', '') for m in agent.messages)
    team.prepare_call(agent)
    assert sum('"team_state"' in m.get('content', '') for m in agent.messages) == count
    assert {t['owner'] for t in team.task_board()} == {'researcher', 'reviewer'}
    trace.close()


def test_nonzero_observation_can_be_shared_as_evidence(tmp_path):
    task, team, trace = build(tmp_path, 'agent_team')
    team.domain['stock'].run = lambda *a: Observation('Exit code: 1\n1 test failed', dict(exit_code=1, error=False))
    team.run_task(task)
    assert 'e1' in team.access['reviewer']
    assert any(e['text'].endswith('1 test failed') for e in team.evidence.values())
    trace.close()


def test_halted_member_snapshot_does_not_block_peer_next_turn(tmp_path):
    import threading
    exporting = threading.Event()
    peer_continued = threading.Event()
    def snapshot(role, revision, paths):
        if role == 'researcher':
            exporting.set()
            assert peer_continued.wait(5)
        return dict(patch=role)
    def respond(messages, tools, choice):
        role = messages[0]['content'].split('Member identity: ')[1].split('.')[0]
        if role == 'researcher':
            raise ProviderError('context_length', 'fixture')
        if role == 'leader':
            return dict(calls=[('wait_for_message', {})])
        assert exporting.wait(5)
        if not any(m['role'] == 'assistant' for m in messages):
            return dict(calls=[('list_tasks', {})])
        peer_continued.set()
        return submit_or_wait(messages)
    task, team, trace = build(tmp_path, 'agent_team', ScriptedClient(respond),
                              scheduler='async', submission_hook=snapshot)
    result = team.run_task(task)
    assert 'snapshot_errors' not in result and team.submitted['reviewer']
    assert peer_continued.is_set()
    trace.close()
