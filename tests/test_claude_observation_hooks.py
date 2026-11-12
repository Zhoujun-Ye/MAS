"""Native observations remain passive after loop-detector retirement."""

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
