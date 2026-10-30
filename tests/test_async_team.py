import json
import threading

import pytest

from fakes import ScriptedClient
from test_agent_team import build, submit_or_wait
from harness.llm import ProviderError
from harness.trace import read_trace, validate
from analysis.information import message_lifecycle, decision_case


def test_leader_and_workers_start_concurrently(tmp_path):
    barrier = threading.Barrier(3, timeout=5)
    def policy(messages, tools, choice):
        if not any(m['role'] == 'assistant' for m in messages):
            barrier.wait()
        return submit_or_wait(messages) if 'submit_assignment' in tools else dict(content='done')
    task, team, trace = build(tmp_path, 'agent_team', ScriptedClient(policy), scheduler='async')
    assert team.run_task(task)['submission_status'] == 'submitted'
    assert team.calls_by_member['leader'] >= 1
    trace.close()


def test_overlapping_calls_and_next_step_delivery(tmp_path):
    started = threading.Barrier(2, timeout=5)
    sent = threading.Event()
    def policy(messages, tools, choice):
        role = messages[0]['content'].split('Reusable role: ')[1].split('.')[0]
        count = sum(m['role'] == 'assistant' for m in messages)
        if role != 'leader' and count == 0:
            started.wait()
            if role == 'reviewer':
                assert sent.wait(5)
                assert 'IMPORTANT_FACT' not in str(messages)
                return dict(calls=[('wait_for_message', {})])
            return dict(calls=[('stock', {})])
        if role == 'researcher' and count == 1:
            return dict(calls=[('send_message', dict(recipient='reviewer', content='IMPORTANT_FACT', evidence_ids=['e1']))])
        if role == 'reviewer':
            assert 'IMPORTANT_FACT' in str(messages)
            assert 'monotonic_ns' not in str(messages)
        return dict(content='done') if role == 'leader' else submit_or_wait(messages)
    task, team, trace = build(tmp_path, 'agent_team', ScriptedClient(policy), scheduler='async')
    original = team.queue
    def queue(*args, **kwargs):
        result = original(*args, **kwargs)
        if args[0:2] == ('researcher', 'reviewer'):
            sent.set()
        return result
    team.queue = queue
    result = team.run_task(task)
    trace.emit('run_end', status=result['status'])
    trace.close()
    assert result['termination'] == 'tasks_submitted'
    events = read_trace(trace.path)
    assert validate(events) == []
    receipt = next(r for r in message_lifecycle(events) if r['receiver'] == 'reviewer')
    assert receipt['source_tool_call_ids'][0]
    assert receipt['sent_ns'] <= receipt['delivered_ns'] <= receipt['consumed_ns']
    starts = [e for e in events if e['type'] == 'model_input' and e['agent'] == 'reviewer']
    assert starts[0]['t'] < receipt['sent_t'] < starts[1]['t']
    case = decision_case(events, 'reviewer', starts[0]['t'])
    row = next(r for r in case['message_lifecycle'] if r['receiver'] == 'reviewer')
    assert row['at_decision'] == 'sent_after_decision'
    assert 'IMPORTANT_FACT' not in str(case['decision_input'])
    later = message_lifecycle(events, starts[1]['t'])
    assert next(r for r in later if r['receiver'] == 'reviewer')['at_decision'] == 'in_model_input'


@pytest.mark.parametrize('cap', [2, 3, 5])
def test_concurrent_reservations_never_exceed_cap(tmp_path, cap):
    task, team, trace = build(tmp_path, 'agent_team', scheduler='async', max_calls=cap)
    result = team.run_task(task)
    assert all(n <= cap for n in team.calls_by_member.values())
    assert result['status'] in ('completed', 'incomplete')
    trace.close()


def test_provider_failure_drains_other_inflight_call(tmp_path):
    barrier = threading.Barrier(2, timeout=5)
    finished = threading.Event()
    def policy(messages, tools, choice):
        role = messages[0]['content'].split('Reusable role: ')[1].split('.')[0]
        if role == 'leader':
            return dict(calls=[('wait_for_message', {})])
        barrier.wait()
        if role == 'researcher':
            raise ProviderError('http_400', 'fixture', 400)
        finished.set()
        return dict(content='done')
    task, team, trace = build(tmp_path, 'agent_team', ScriptedClient(policy), scheduler='async')
    with pytest.raises(ProviderError):
        team.run_task(task)
    assert finished.is_set()
    trace.close()


def test_domain_tools_really_overlap(tmp_path):
    barrier = threading.Barrier(2, timeout=5)
    def policy(messages, tools, choice):
        count = sum(m['role'] == 'assistant' for m in messages)
        if 'stock' in tools and count == 0:
            return dict(calls=[('stock', {})])
        return submit_or_wait(messages) if 'submit_assignment' in tools else dict(content='done')
    task, team, trace = build(tmp_path, 'agent_team', ScriptedClient(policy), scheduler='async')
    team.permissions['reviewer'] = ('stock',)
    original = team.domain['stock'].run
    def tool(args, agent):
        barrier.wait()
        return original(args, agent)
    team.domain['stock'].run = tool
    assert team.run_task(task)['status'] == 'completed'
    assert sum(b.used for b in team.budgets.values()) == 2 and len(team.evidence) == 2
    trace.close()


def test_completion_reports_during_inflight_turns_do_not_lose_final_wakeup(tmp_path):
    def policy(messages, tools, choice):
        if 'submit_assignment' in tools:
            return dict(calls=[('submit_assignment', dict(report='Complete'))])
        return dict(content='done')
    for i in range(25):
        task, team, trace = build(tmp_path / str(i), 'agent_team', ScriptedClient(policy), scheduler='async')
        assert team.run_task(task)['termination'] == 'tasks_submitted'
        trace.close()


def test_submission_snapshot_io_does_not_serialize_peers(tmp_path):
    barrier = threading.Barrier(2, timeout=5)
    def snapshot(role, revision, paths):
        barrier.wait()
        return dict(patch=role, revision=revision)
    def policy(messages, tools, choice):
        if 'submit_assignment' in tools:
            return dict(calls=[('submit_assignment', dict(report='Submit', paths=[]))])
        return dict(content='Submit')
    task, team, trace = build(tmp_path, 'agent_team', ScriptedClient(policy), scheduler='async',
                              submission_hook=snapshot)
    result = team.run_task(task)
    assert result['submission_status'] == 'submitted'
    assert team.evaluation_snapshots['researcher']['artifact']['patch'] == 'researcher'
    trace.close()
