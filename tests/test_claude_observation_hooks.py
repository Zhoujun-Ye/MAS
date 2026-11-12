"""Passive loop observations and explicit native delegation permissions."""

import inspect
import json
import subprocess
import sys

import pytest

from harness import ClaudeCodeSingleAgentCLI, ClaudeCodeSubagentsCLI
from harness import _claude_hooks


@pytest.mark.parametrize('single,worker', [(True, False), (False, False), (False, True)])
def test_repeated_calls_only_record_events_without_loop_state(tmp_path, single, worker):
    output=tmp_path/'events.jsonl'
    argv=[sys.executable, '-I', _claude_hooks.__file__, '--output', str(output)]
    if single:
        argv.append('--single-agent')
    for i in range(12):
        payload=dict(hook_event_name='PostToolUse', session_id='root',
            tool_use_id=f'call-{i}', transcript_path='/native/root.jsonl',
            tool_name='Read', tool_input=dict(file_path='/workspace/a'), tool_response='same')
        if worker:
            payload['agent_id']='worker'
        result=subprocess.run(argv,input=json.dumps(payload),text=True,capture_output=True,check=True)
        assert json.loads(result.stdout)=={}
    rows=[json.loads(line) for line in output.read_text().splitlines()]
    assert len(rows)==12 and all('loop_detection' not in row for row in rows)
    assert sorted(p.name for p in tmp_path.iterdir())==['events.jsonl']


@pytest.mark.parametrize('adapter', [ClaudeCodeSingleAgentCLI, ClaudeCodeSubagentsCLI])
def test_adapter_plan_has_no_loop_option_or_host_monitor(tmp_path, adapter):
    work=tmp_path/'work';work.mkdir()
    assert 'loop_guard_mode' not in inspect.signature(adapter.run).parameters
    plan=adapter().run('task',model='fake',workspace=work,output=tmp_path/'out')
    assert 'termination_file' not in plan and 'termination_policy' not in plan
    settings=json.loads(plan['argv'][plan['argv'].index('--settings')+1])
    hooks=settings['hooks']
    assert 'SessionStart' in hooks and 'SubagentStop' in hooks
    assert all('--loop-mode' not in item['command'] for entries in hooks.values()
               for entry in entries for item in entry['hooks'])
    assert not (tmp_path/'out').exists()


def gate(event, state, **values):
    payload = dict(hook_event_name=event, session_id='root', **values)
    decision = _claude_hooks.required_delegation_decision(payload, state)
    return decision, payload['mandatory_delegation']


def started_state():
    state = {}
    gate('SessionStart', state)
    return state


@pytest.mark.parametrize('tool', ['Bash', 'Write', 'Edit', 'NotebookEdit', 'SendMessage', 'ListAgents', 'TaskStop'])
def test_lead_cannot_execute_or_write_before_native_worker_start(tool):
    decision, observation = gate('PreToolUse', started_state(), tool_name=tool, tool_use_id='blocked')
    assert decision['hookSpecificOutput']['permissionDecision'] == 'deny'
    assert observation['action'] == 'tool_denied'


@pytest.mark.parametrize('tool', _claude_hooks.DELEGATION_POLICY['initial_tools'])
def test_initial_read_only_planning_and_delegation_remain_available(tool):
    decision, _ = gate('PreToolUse', started_state(), tool_name=tool, tool_use_id='allowed')
    assert decision == {}


def test_attempted_or_failed_delegation_does_not_unlock_gate():
    state = started_state()
    gate('PreToolUse', state, tool_name='Agent', tool_use_id='failed', tool_input={'subagent_type': 'general-purpose'})
    assert gate('PreToolUse', state, tool_name='Bash')[0]
    gate('PostToolUseFailure', state, tool_name='Agent', tool_use_id='failed')
    gate('SubagentStart', state, agent_id='internal', agent_type='general-purpose')
    assert gate('PreToolUse', state, tool_name='Write')[0]


@pytest.mark.parametrize('tool', ['Agent', 'Task'])
def test_only_matching_native_worker_start_unlocks_lead(tool):
    state = started_state()
    gate('PreToolUse', state, tool_name=tool, tool_use_id='spawn', tool_input={'subagent_type': 'general-purpose'})
    gate('SubagentStop', state, agent_id='summarizer', agent_type='')
    gate('SubagentStart', state, agent_id='wrong', agent_type='Explore')
    assert gate('Stop', state)[0]['decision'] == 'block'
    gate('SubagentStart', state, agent_id='worker', agent_type='general-purpose')
    assert gate('PreToolUse', state, tool_name='Bash')[0] == {}
    gate('SubagentStop', state, agent_id='worker', agent_type='general-purpose')
    assert gate('Stop', state)[0] == {}
    assert state['sessions']['root']['started'] == ['worker']


def test_worker_tools_and_worker_stops_are_not_blocked():
    state = started_state()
    assert gate('PreToolUse', state, tool_name='Bash', agent_id='worker')[0] == {}
    assert gate('Stop', state, agent_id='worker')[0] == {}
    assert gate('SubagentStop', state, agent_id='worker')[0] == {}


@pytest.mark.parametrize('tool', ['Agent', 'Task'])
@pytest.mark.parametrize('status', ['async_launched', 'completed'])
def test_native_tool_return_before_start_retains_identity_join(tool, status):
    state = started_state()
    gate('PreToolUse', state, tool_name=tool, tool_use_id='spawn', tool_input={'subagent_type': 'Explore'})
    gate('PostToolUse', state, tool_name=tool, tool_use_id='spawn',
         tool_response=dict(status=status, agentId='worker'))
    assert gate('PreToolUse', state, tool_name='Bash')[0]
    gate('SubagentStart', state, agent_id='unrelated', agent_type='Explore')
    assert gate('PreToolUse', state, tool_name='Bash')[0]
    gate('SubagentStart', state, agent_id='worker', agent_type='Explore')
    assert gate('PreToolUse', state, tool_name='Bash')[0] == {}
    assert state['sessions']['root']['started'] == ['worker']


def test_stop_hook_active_is_not_a_delegation_bypass():
    decision, observation = gate('Stop', started_state(), stop_hook_active=True)
    assert decision['decision'] == 'block' and observation['action'] == 'stop_blocked'


def test_new_native_session_does_not_inherit_previous_delegation():
    state = started_state()
    gate('PreToolUse', state, tool_name='Agent', tool_use_id='spawn')
    gate('SubagentStart', state, agent_id='worker', agent_type='general-purpose')
    payload = dict(hook_event_name='SessionStart', session_id='new-root')
    _claude_hooks.required_delegation_decision(payload, state)
    payload.update(hook_event_name='PreToolUse', tool_name='Bash')
    assert _claude_hooks.required_delegation_decision(payload, state)['hookSpecificOutput']['permissionDecision'] == 'deny'


def test_subagents_enable_policy_but_single_stays_strictly_single(tmp_path):
    from harness._claude_cli import hook_settings
    for adapter, required, single in ((ClaudeCodeSubagentsCLI, True, False), (ClaudeCodeSingleAgentCLI, False, True)):
        work = tmp_path/adapter.__name__
        work.mkdir()
        plan = adapter().run('task', model='fake', workspace=work, output=tmp_path/(adapter.__name__+'-out'),
                             settings={'disableAllHooks': True})
        native = json.loads(plan['argv'][plan['argv'].index('--settings')+1])
        assert native['disableAllHooks'] is False
        commands = [h['command'] for entries in native['hooks'].values() for entry in entries for h in entry['hooks']]
        assert all(('--require-delegation' in c) is required for c in commands)
        assert all(('--single-agent' in c) is single for c in commands)
    with pytest.raises(ValueError, match='Single'):
        hook_settings(tmp_path, '/fixture', single_agent=True, require_delegation=True)


def invoke_required_hook(output, **payload):
    result = subprocess.run([sys.executable, '-I', _claude_hooks.__file__, '--output', str(output),
        '--require-delegation'], input=json.dumps(dict(session_id='root', **payload)),
        text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


def test_hook_state_is_atomic_under_concurrent_native_events(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    output = tmp_path/'events.jsonl'
    invoke_required_hook(output, hook_event_name='SessionStart')
    invoke_required_hook(output, hook_event_name='PreToolUse', tool_name='Agent', tool_use_id='spawn')
    invoke_required_hook(output, hook_event_name='SubagentStart', agent_id='worker', agent_type='general-purpose')
    def call(index):
        return invoke_required_hook(output, hook_event_name='PreToolUse', tool_name='Bash',
                                    tool_use_id=f'call-{index}', agent_id='worker')
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert all(value == {} for value in pool.map(call, range(16)))
    rows = [json.loads(line) for line in output.read_text().splitlines()]
    assert len(rows) == 19
    state = json.loads((tmp_path/'delegation-state.json').read_text())
    assert state['sessions']['root']['started'] == ['worker']
    assert not (tmp_path/'delegation-state.tmp').exists()


@pytest.mark.parametrize('corruption', ['missing', 'invalid-json', 'symlink'])
def test_missing_or_corrupt_policy_state_fails_closed(tmp_path, corruption):
    output = tmp_path/'events.jsonl'
    invoke_required_hook(output, hook_event_name='SessionStart')
    state = tmp_path/'delegation-state.json'
    state.unlink()
    if corruption == 'invalid-json':
        state.write_text('broken')
    elif corruption == 'symlink':
        target = tmp_path/'unrelated'
        target.write_text('do not overwrite')
        state.symlink_to(target)
    result = invoke_required_hook(output, hook_event_name='PreToolUse', tool_name='Bash')
    assert result['continue'] is False
    assert json.loads(output.read_text().splitlines()[-1])['mandatory_delegation']['action'] == 'policy_error'
    if corruption == 'symlink':
        assert target.read_text() == 'do not overwrite'


def test_native_audit_requires_complete_policy_evidence(tmp_path):
    from analysis.native_evidence import native_subagents
    output = tmp_path/'native-profile/observer/events.jsonl'
    for event in (
            dict(hook_event_name='SessionStart'),
            dict(hook_event_name='PreToolUse', tool_name='Agent', tool_use_id='spawn'),
            dict(hook_event_name='SubagentStart', agent_id='worker', agent_type='general-purpose'),
            dict(hook_event_name='SubagentStop', agent_id='worker', agent_type='general-purpose'),
            dict(hook_event_name='Stop'), dict(hook_event_name='SessionEnd')):
        invoke_required_hook(output, **event)
    audit = native_subagents(tmp_path)
    assert audit['passed'] and audit['mandatory_delegation']['passed']
    rows = [json.loads(line) for line in output.read_text().splitlines()]
    rows[1].pop('mandatory_delegation')
    output.write_text('\n'.join(map(json.dumps, rows)))
    audit = native_subagents(tmp_path)
    assert not audit['passed'] and not audit['mandatory_delegation']['measured']
    rows[1]['mandatory_delegation'] = dict(version='native-delegation-v1', action='policy_error')
    output.write_text('\n'.join(map(json.dumps, rows)))
    assert native_subagents(tmp_path)['mandatory_delegation']['errors'] == 1
