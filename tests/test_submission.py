import json
from dataclasses import FrozenInstanceError

import pytest

from fakes import ScriptedClient
from test_agent_team import build
from harness.information import CommunicationPolicy
from harness.trace import read_trace


def submit_policy(messages, tools, choice):
    if 'submit_assignment' in tools and choice != 'none':
        return dict(calls=[('submit_assignment', dict(report='PRIVATE_REPORT', paths=[]))])
    return dict(content='Final report, not verified success')


@pytest.mark.parametrize('scheduler', ['controlled', 'async'])
def test_mutating_tool_automatically_reopens_submission(tmp_path, scheduler):
    def policy(messages, tools, choice):
        reply = submit_policy(messages, tools, choice)
        if 'stock' in tools and not any(m['role'] == 'assistant' for m in messages):
            reply['calls'].append(('stock', {}))
        return reply
    task, team, trace = build(tmp_path, 'agent_team', ScriptedClient(policy), scheduler=scheduler)
    result = team.run_task(task)
    assert result['submission_status'] == 'submitted'
    assert result['verification']['status'] == 'not_run'
    assert sum(b.used for b in team.budgets.values()) == 1 and team.evidence
    assert team.tasks['researcher']['revision'] == 2
    assert set(team.agent_states.values()) == {'terminated'}
    assert team.tasks['researcher']['status'] == 'submitted'
    trace.close()


def test_snapshots_reopen_and_evaluator_ownership(tmp_path):
    artifact = dict(patch='first')
    task, team, trace = build(tmp_path, 'agent_team', ScriptedClient(submit_policy),
                              submission_hook=lambda role, revision, paths: artifact)
    team.run_task(task)
    first = team.submission('researcher')
    artifact['patch'] = 'later mutable workspace'
    first['artifact']['patch'] = 'aliased mutation'
    assert team.submission('researcher')['artifact']['patch'] == 'first'
    team.record_verification('researcher', 'researcher:v1', 'passed')
    assert team.tasks['researcher']['status'] == 'completed'
    assert 'record_verification' not in team.agents['researcher'].tools
    team.queue('reviewer', 'researcher', 'FYI only', [])
    team.receive('researcher')
    assert team.submitted['researcher'] and team.tasks['researcher']['revision'] == 1
    team.update_task('researcher', 'working')
    assert not team.submitted['researcher'] and team.tasks['researcher']['revision'] == 2
    assert team.tasks['researcher']['verification'] == 'not_run'
    with pytest.raises(ValueError, match='No current'):
        team.submission('researcher')
    with pytest.raises(ValueError, match='current submitted'):
        team.record_verification('researcher', 'researcher:v1', 'passed')
    team.submit_assignment(team.agents['researcher'], 'new report', [], paths=[])
    assert team.submission('researcher')['artifact']['patch'] == 'later mutable workspace'
    assert json.loads(team.submission_history['researcher:v1'])['artifact']['patch'] == 'first'
    with pytest.raises(ValueError, match='current submitted'):
        team.record_verification('researcher', 'researcher:v1', 'passed')
    team.record_verification('researcher', 'researcher:v2', 'failed')
    assert team.tasks['researcher']['status'] == 'submitted'
    assert team.tasks['researcher']['verification'] == 'failed'
    trace.close()


def test_snapshot_failure_does_not_submit(tmp_path):
    task, team, trace = build(tmp_path, 'agent_team', ScriptedClient(submit_policy))
    team.run_task(task)
    team.update_task('researcher', 'working')
    def broken(role, revision, paths):
        raise RuntimeError('snapshot failed')
    team.submission_hook = broken
    with pytest.raises(RuntimeError, match='snapshot failed'):
        team.submit_assignment(team.agents['researcher'], 'not a snapshot', [], paths=[])
    assert not team.submitted['researcher']
    assert team.tasks['researcher']['submission_id'] is None
    assert 'researcher:v2' not in team.submission_history
    trace.close()


def test_metadata_notifications_do_not_bypass_message_policy_or_budget(tmp_path):
    task, team, trace = build(tmp_path, 'agent_team', ScriptedClient(submit_policy), max_messages=1)
    result = team.run_task(task)
    assert result['termination'] == 'tasks_submitted'
    assert team.submitted['reviewer']  # Snapshot precedes a rejected report.
    events = [json.loads(m['content'])['task_event'] for m in team.agents['leader'].messages
              if m['role'] == 'user' and '"task_event"' in m['content']]
    assert {event['owner'] for event in events} == {'researcher', 'reviewer'}
    expected = {'type', 'task_id', 'owner', 'status', 'revision', 'submission_id'}
    assert all(set(event) == expected for event in events)
    assert 'PRIVATE_REPORT' not in json.dumps(events + team.task_board())
    assert team.sent == 2
    trace.close()


def test_policy_is_frozen_recorded_and_shared_by_all_content_paths(tmp_path):
    policy = CommunicationPolicy(version='fixture-v1', instructions='Preserve uncertainty.')
    with pytest.raises(FrozenInstanceError):
        policy.instructions = 'mutate'
    task, team, trace = build(tmp_path, 'agent_team', communication_policy=policy)
    result = team.run_task(task)
    assert result['submission_status'] == 'submitted'
    assert team.control['communication_policy'] == policy.manifest
    assert all(a.messages[0]['content'].endswith(policy.instructions) for a in team.agents.values())
    trace.close()
    events = read_trace(trace.path)
    outgoing = [e for e in events if e['type'] == 'peer_queued']
    policy_events = [e for e in events if e['type'] == 'policy_message']
    assert len(outgoing) == len(policy_events) >= 3
    assert {e['sender'] for e in outgoing} >= {'researcher', 'reviewer'}
    task, other, other_trace = build(tmp_path / 'other', 'agent_team')
    assert other.control_digest != team.control_digest
    other_trace.close()


@pytest.mark.parametrize('scheduler', ['controlled', 'async'])
def test_finalization_waits_for_awakened_submitted_worker(tmp_path, scheduler):
    def policy(messages, tools, choice):
        role = messages[0]['content'].split('Reusable role: ')[1].split('.')[0]
        count = sum(m['role'] == 'assistant' for m in messages)
        if role == 'leader':
            if count == 0:
                return dict(calls=[('send_message', dict(recipient='researcher', content='Please check'))])
            return dict(content='Final')
        if role == 'researcher' and count == 1:
            return dict(calls=[('read_evidence', dict(id='e999'))])
        if role == 'researcher' and count == 2:
            return dict(calls=[('send_message', dict(recipient='leader', content='AFTER_CHECK')),
                               ('wait_for_message', {})])
        return dict(calls=[('submit_assignment', dict(report='Initial report'))])
    task, team, trace = build(tmp_path, 'agent_team', ScriptedClient(policy), scheduler=scheduler)
    result = team.run_task(task)
    assert result['termination'] == 'tasks_submitted'
    leader_inputs = [r[0] for r in team.client.requests if r[0][0]['content'].startswith('Reusable role: leader.')]
    assert 'AFTER_CHECK' in str(leader_inputs[-1])
    assert team.tasks['researcher']['revision'] == 1
    trace.close()


def test_partial_budget_final_cannot_invoke_verifier(tmp_path):
    def forbidden(submissions):
        pytest.fail('Partial submission must not be verified')
    task, team, trace = build(tmp_path, 'agent_team', max_calls=2, verifier=forbidden)
    result = team.run_task(task)
    assert result['failure_class'] == 'agent_failure'
    assert result['submission_status'] == 'incomplete'
    assert result['verification']['status'] == 'not_run'
    trace.close()
