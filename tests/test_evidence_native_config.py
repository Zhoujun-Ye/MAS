import json
from pathlib import Path
import sys

import pytest

from harness import ClaudeCodeSubagentsCLI, ClaudeCodeSingleAgentCLI
from harness.evidence_mas.cli import EvidenceMASCLI
from harness.evidence_mas.cli import workspace_guidance
from scripts.common.evidence import lead_prompt
from scripts.common.prompts.native_subagents import PROMPT as NATIVE_PROMPT
from scripts.common.prompts.structured_subagents import PROMPT as STRUCTURED_PROMPT
from harness.evidence_mas.hook import response
from harness.evidence_mas.mcp import Server
from harness.evidence_mas.store import Store, StoreError
from scripts.probes.evidence_mas import Fixture


def config(tmp_path, **kwargs):
    return EvidenceMASCLI().command('fixture', store_root=str(tmp_path/'store'), run_id='fixture',
        task_rules='No network. Time limit 60 seconds.', observer_target=str(tmp_path/'observer'),
        python=sys.executable, **kwargs)


def test_baseline_commands_unchanged_and_configuration_pure(tmp_path):
    baselines = [ClaudeCodeSingleAgentCLI(), ClaudeCodeSubagentsCLI()]
    before = [b.command('fixture', isolated_settings=True) for b in baselines]
    source = {'hooks': {'PreToolUse': [{'hooks': [{'type': 'command', 'command': 'original'}]}]}}
    copy = json.loads(json.dumps(source))
    argv = config(tmp_path, settings=source)
    assert source == copy
    assert before == [b.command('fixture', isolated_settings=True) for b in baselines]
    assert not (tmp_path/'store').exists()
    settings = json.loads(argv[argv.index('--settings')+1])
    assert len(settings['hooks']['PreToolUse']) == 3
    assert settings['env']['CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS'] == '0'
    assert argv[argv.index('--permission-mode')+1] == 'default'
    assert 'evidence' in json.loads(argv[argv.index('--mcp-config')+1])['mcpServers']


@pytest.mark.parametrize('mode', ['full', 'observations'])
def test_worker_tools_shared_rules_and_role_server(tmp_path, mode):
    argv = config(tmp_path, mode=mode)
    worker = json.loads(argv[argv.index('--agents')+1])['evidence-worker']
    assert 'No network. Time limit 60 seconds.' in worker['prompt']
    assert not any(name.endswith('__ledger_record_selection') for name in worker['tools'])
    assert worker['mcpServers'][0]['evidence_worker']['args'][-1] == mode
    if mode == 'observations':
        assert not any('__ledger_' in name for name in worker['tools'])


def test_plan_does_not_launch_or_write(tmp_path):
    work = tmp_path/'work'
    work.mkdir()
    plan = EvidenceMASCLI().run('task', model='fixture', workspace=work, output=tmp_path/'output',
        store_root=tmp_path/'store', run_id='fixture', task_rules='No network', python=sys.executable)
    assert plan['status'] == 'planned'
    assert not (tmp_path/'output').exists() and not (tmp_path/'store').exists()


def test_worker_guard_and_observation_context():
    event = dict(hook_event_name='PreToolUse', agent_id='worker', tool_name='mcp__evidence__ledger_record_selection')
    assert response(event, None)['hookSpecificOutput']['permissionDecision'] == 'deny'
    event.pop('agent_id')
    assert response(event, None) == {}
    assert response(dict(hook_event_name='PostToolUse'), {'id': 'obs1'}) == {}


def test_observations_mode_cannot_call_hidden_tools_or_change_mode(tmp_path):
    store = Store(tmp_path/'store', 'r')
    server = Server(store, 'lead', 'lead', 'observations')
    server.handle(dict(jsonrpc='2.0', id=1, method='initialize'))
    result = server.handle(dict(jsonrpc='2.0', id=2, method='tools/call',
        params=dict(name='ledger_open_issue', arguments=dict(question='q', source_refs=[], analysis_scope='x'))))
    assert 'error' in result
    with pytest.raises(StoreError):
        Server(store, 'lead', 'lead', 'full')


def test_disabled_hooks_rejected(tmp_path):
    with pytest.raises(ValueError):
        config(tmp_path, settings={'disableAllHooks': True})


def test_modes_use_native_organization_and_share_only_tool_guidance(tmp_path):
    for mode in ('observations','full'):
        assert lead_prompt(mode) == NATIVE_PROMPT + '\n\n' + workspace_guidance(mode)
        worker = json.loads(config(tmp_path, mode=mode)[-1])['evidence-worker']
        assert worker['prompt'].startswith(workspace_guidance(mode))
        assert STRUCTURED_PROMPT not in worker['prompt']
        assert 'check task-required' not in lead_prompt(mode)
        with pytest.raises(ValueError,match='native delegation'):
            config(tmp_path,mode=mode,disallowed_tools=('Task',))


def test_fixture_waits_and_refreshes_after_native_notification():
    fixture = Fixture('legacy-full')
    results = [('shell', {}), ('list', {'items': [{'id': 'a'*32}]}), ('read', {}),
               ('issue', {'kind': 'issue', 'id': 'b'*32}), ('delegate', {}), ('view-0', {'candidates': []})]
    body = dict(system='lead', messages=[dict(role='user', content=[dict(type='tool_result',
                tool_use_id='fixture-lead-'+name, content=json.dumps(value)) for name, value in results])])
    assert fixture.next(body)['type'] == 'text'
    body['messages'].append(dict(role='user', content='Worker completed shared evidence registration.'))
    block = fixture.next(body)
    assert block['name'] == 'mcp__evidence__ledger_view' and block['id'] == 'fixture-lead-view-1'
