import json

from scripts.kramabench.run import admission
from scripts.kramabench.cli_runtime import backend_instructions, options


def test_authorized_conditions_are_explicit():
    assert options("deepagents")["single_agent"] is True
    assert options("deepagents")["max_turns"] == 500
    assert "SINGLE-AGENT" in backend_instructions("deepagents")
    assert "do not sleep" in backend_instructions("claude-code-agent-team")
    assert "Agent Teams is disabled" in backend_instructions("claude-code-subagents")


def test_single_admission_requires_native_policy_proof_and_valid_artifact(tmp_path):
    work = tmp_path / "task/deepagents/workspace"
    work.mkdir(parents=True)
    (work / "pipeline.py").write_text("print(1)")
    (work / "submission.json").write_text(json.dumps(dict(answer=1, pipeline_path="pipeline.py",
                                                       evidence="fixture", unfinished=[])))
    row = dict(task_id="task", backend="deepagents", status="cli_exited")
    assert not admission(tmp_path, row)["passed"]
    row["single_agent_audit"] = dict(passed=True)
    assert admission(tmp_path, row)["passed"]


def test_team_admission_requires_native_completion_not_plain_exit(tmp_path):
    folder = tmp_path/'task/claude-code'
    work = folder/'workspace'
    work.mkdir(parents=True)
    (work/'pipeline.py').write_text('print(1)')
    (work/'submission.json').write_text(json.dumps(dict(answer=1, pipeline_path='pipeline.py',
                                                      evidence='fixture', unfinished=[])))
    row = dict(task_id='task', backend='claude-code', status='cli_exited', cli={})
    assert not admission(tmp_path, row)['passed']
    (folder/'cli').mkdir()
    (folder/'cli/native-team-before-exit.json').write_text(json.dumps([dict(data=dict(
        members=[dict(name='checker', agentType='general-purpose')]))]))
    row['cli'] = dict(native_before_exit=dict(ready_to_exit=True, pending_native_input=False),
                      native_lifecycle=dict(root_session_end_observed=True), completion_file_observed=True)
    assert admission(tmp_path, row)['passed']
    row['cli']['native_before_exit']['pending_native_input'] = True
    assert not admission(tmp_path, row)['passed']


def test_subagents_admission_needs_real_delegation_and_no_team(tmp_path):
    folder = tmp_path/'task/claude-code-subagents'
    work = folder/'workspace'
    work.mkdir(parents=True)
    (work/'pipeline.py').write_text('print(1)')
    (work/'submission.json').write_text(json.dumps(dict(answer=1, pipeline_path='pipeline.py',
                                                      evidence='fixture', unfinished=[])))
    events = folder/'native-profile/observer/events.jsonl'
    events.parent.mkdir(parents=True)
    rows = [dict(hook_event_name='SessionStart', session_id='root'),
            dict(hook_event_name='SessionEnd', session_id='root')]
    report = dict(task_id='task', backend='claude-code-subagents', status='cli_exited')
    events.write_text('\n'.join(map(json.dumps, rows)))
    assert not admission(tmp_path, report)['passed']
    rows[1:1] = [dict(hook_event_name='SubagentStart', agent_id='worker'),
                 dict(hook_event_name='SubagentStop', agent_id='worker')]
    events.write_text('\n'.join(map(json.dumps, rows)))
    assert admission(tmp_path, report)['passed']
    rows.append(dict(hook_event_name='TeammateIdle'))
    events.write_text('\n'.join(map(json.dumps, rows)))
    assert not admission(tmp_path, report)['passed']
