import json
import pytest

from harness import ClaudeCodeSubagentsCLI
from analysis.native_evidence import native_subagents


def test_native_modes_cannot_be_switched_by_settings():
    sub = ClaudeCodeSubagentsCLI().command('model', settings=dict(env=dict(CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS='1')))
    settings = json.loads(sub[sub.index('--settings')+1])
    assert settings['env']['CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS'] == '0'
    assert '--print' in sub
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


@pytest.mark.parametrize('killer', ['parent', 'system', 'user'])
def test_native_killed_worker_is_accounted_without_stop_hook(tmp_path, killer):
    path = tmp_path/'native-profile/observer/events.jsonl'
    path.parent.mkdir(parents=True)
    rows = [dict(hook_event_name='SessionStart', session_id='root'),
            dict(hook_event_name='SubagentStart', agent_id='worker'),
            dict(hook_event_name='SessionEnd', session_id='root')]
    path.write_text('\n'.join(map(json.dumps, rows)))
    killed = dict(parent=0, user=0, system=0)
    killed[killer] = 1
    native = dict(session_id='root', terminal_reason='completed', is_error=False,
                  subagent_stats=dict(spawned=1, completed=0, failed=0, killed=killed))
    report = dict(cli=dict(status='cli_exited', returncode=0, native_result=native))
    target = tmp_path/'report.json'
    target.write_text(json.dumps(report))
    audit = native_subagents(tmp_path)
    assert audit['passed'] and audit['structural_delegation_complete']
    assert audit['active_subagent_ids'] == ['worker']  # Hook evidence is not rewritten.
    assert audit['workspace_quiescence'] == 'unverified'
    for field, value in [('session_id', 'other'), ('terminal_reason', 'failed'), ('is_error', True)]:
        changed = dict(native, **{field: value})
        target.write_text(json.dumps(dict(cli=dict(report['cli'], native_result=changed))))
        assert not native_subagents(tmp_path)['passed']
    native['subagent_stats']['killed'][killer] = 2
    target.write_text(json.dumps(report))
    assert not native_subagents(tmp_path)['passed']
