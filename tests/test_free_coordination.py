import pytest

from fakes import ScriptedClient
from test_agent_team import build


def test_free_exchange_has_no_message_or_model_round_cap(tmp_path):
    def policy(messages, tools, choice):
        role = messages[0]['content'].split('Member identity: ')[1].split('.')[0]
        count = sum(m['role'] == 'assistant' for m in messages)
        if role == 'researcher':
            if count < 45:
                return dict(calls=[('send_message', dict(recipient='reviewer', content=f'Discussion {count}'))])
            return dict(calls=[('submit_assignment', dict(report='Ready'))])
        if role == 'reviewer':
            if 'Discussion 44' not in str(messages):
                return dict(calls=[('wait_for_message', {})])
            return dict(calls=[('submit_assignment', dict(report='Ready'))])
        return dict(content='Final')
    task, team, trace = build(tmp_path, 'agent_team', ScriptedClient(policy),
                              max_calls=None, max_messages=None, max_reads=None,
                              token_budget=None, time_limit_seconds=60)
    result = team.run_task(task)
    assert result['submission_status'] == 'submitted'
    assert team.calls_by_member['researcher'] == 46
    assert team.messages_by_member['researcher'] == 46
    assert team.tokens_by_member['researcher'] > 200_000
    assert 'token_limit' not in result.get('halted_members', {}).values()
    trace.close()


def test_cooperbench_keeps_tool_and_time_limits_without_token_cap():
    from benchmarks.cooperbench.adapter import LIMITS, MEMBER_LIMITS
    assert LIMITS['token_budget'] is None
    assert LIMITS['time_limit_seconds'] == 7200
    assert MEMBER_LIMITS['worker_a']['tool_budget'] is MEMBER_LIMITS['worker_b']['tool_budget'] is None
    assert MEMBER_LIMITS['leader']['tool_budget'] == 0


@pytest.mark.parametrize('scheduler', ['controlled', 'async'])
def test_token_budget_stops_free_exchange_and_retains_partial_snapshot(tmp_path, scheduler):
    task, team, trace = build(tmp_path, 'agent_team', ScriptedClient(lambda *a: dict(calls=[('list_tasks', {})])),
                              scheduler=scheduler, max_calls=None, max_messages=None, max_reads=None,
                              token_budget=500, submission_hook=lambda r, v, p: dict(patch='partial'))
    result = team.run_task(task)
    assert result['failure_class'] == 'agent_failure'
    assert 'token_limit' in result['halted_members'].values()
    assert set(result['evaluation_snapshots']) == {'researcher', 'reviewer'}
    assert all(row['tokens'] > 0 for r, row in result['member_usage'].items() if r != 'leader')
    trace.close()


def test_time_budget_is_an_agent_limit_not_external_interruption(tmp_path):
    import time
    def policy(*args):
        time.sleep(0.02)
        return dict(calls=[('stock', {})])
    task, team, trace = build(tmp_path, 'agent_team', ScriptedClient(policy), time_limit_seconds=0.01)
    result = team.run_task(task)
    assert result['reason'] == 'time_limit' and result['failure_class'] == 'agent_failure'
    assert sum(b.used for b in team.budgets.values()) == 0
    trace.close()
