import json

from harness import ClaudeCodeAgentTeamCLI, ClaudeCodeSubagentsCLI
from scripts.kramabench.native_evidence import native_subagents


def test_native_modes_cannot_be_switched_by_settings():
    sub = ClaudeCodeSubagentsCLI().command('model', settings=dict(env=dict(CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS='1')))
    team = ClaudeCodeAgentTeamCLI().command('model', settings=dict(env=dict(CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS='0')))
    for command, flag in ((sub,'0'), (team,'1')):
        settings = json.loads(command[command.index('--settings')+1])
        assert settings['env']['CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS'] == flag
    assert '--print' in sub and '--print' not in team
    assert 'teammateMode' not in json.loads(sub[sub.index('--settings')+1])


def test_subagent_audit_requires_returned_workers_and_no_team(tmp_path):
    profile = tmp_path/'native-profile'
    path = profile/'observer/events.jsonl'
    path.parent.mkdir(parents=True)
    events = [dict(hook_event_name='SessionStart',session_id='root'),
              dict(hook_event_name='SubagentStart',session_id='root',agent_id='worker'),
              dict(hook_event_name='SessionEnd',session_id='root')]
    path.write_text('\n'.join(json.dumps(e) for e in events))
    assert not native_subagents(tmp_path)['passed']
    events.insert(2,dict(hook_event_name='SubagentStop',session_id='root',agent_id='worker'))
    path.write_text('\n'.join(json.dumps(e) for e in events))
    assert native_subagents(tmp_path)['passed']
    events.insert(3,dict(hook_event_name='SubagentStart',session_id='root',agent_id='worker'))
    path.write_text('\n'.join(json.dumps(e) for e in events))
    assert not native_subagents(tmp_path)['passed']


def test_subagents_plans_have_teams_disabled_and_no_side_effects(tmp_path):
    work = tmp_path/'work'
    work.mkdir()
    plan = ClaudeCodeSubagentsCLI().run('task',model='deepseek-flash[1m]',workspace=work,output=tmp_path/'out')
    assert plan['backend'] == 'claude-code-subagents'
    assert plan['environment_overrides']['CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS'] == '0'
    assert not (tmp_path/'out').exists()
