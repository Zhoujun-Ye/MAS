import json
import pytest

from scripts.kramabench.run import admission
from scripts.common.runtime import backend_instructions, options


def test_authorized_conditions_are_explicit():
    assert "Agent" not in options("claude-code-single-agent")["allowed_tools"]
    assert "SINGLE-AGENT" in backend_instructions("claude-code-single-agent")
    subagents = backend_instructions("claude-code-subagents")
    assert subagents.startswith("Use Claude Code's native subagents in an orchestrator-worker organization.")
    assert "Subagents are your primary team and perform the substantive work" in subagents
    assert "Deploy subagents with the native Agent tool" in subagents
    assert "use at least one" in subagents
    assert "Wait for their results through the native tools rather than shell polling" in subagents


def test_single_admission_requires_native_policy_proof_and_valid_artifact(tmp_path, monkeypatch):
    work = tmp_path / "task/claude-code-single-agent/workspace"
    work.mkdir(parents=True)
    (work / "pipeline.py").write_text("print(1)")
    (work / "submission.json").write_text(json.dumps(dict(answer=1, pipeline_path="pipeline.py",
                                                       evidence="fixture", unfinished=[])))
    row = dict(task_id="task", backend="claude-code-single-agent", status="cli_exited")
    assert not admission(tmp_path, row)["passed"]
    monkeypatch.setattr("scripts.kramabench.run.native_single_agent", lambda folder: dict(passed=True))
    assert admission(tmp_path, row)["passed"]


def test_retired_team_admission_is_rejected(tmp_path):
    folder = tmp_path/'task/claude-code'
    work = folder/'workspace'
    work.mkdir(parents=True)
    (work/'pipeline.py').write_text('print(1)')
    (work/'submission.json').write_text(json.dumps(dict(answer=1, pipeline_path='pipeline.py',
                                                      evidence='fixture', unfinished=[])))
    row = dict(task_id='task', backend='claude-code', status='cli_exited', cli={})
    with pytest.raises(ValueError, match="Unsupported backend"):
        admission(tmp_path, row)


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
