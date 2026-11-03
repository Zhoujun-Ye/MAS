import json
import subprocess
import sys

import pytest

from harness import ClaudeCodeSingleAgentCLI
from harness._claude_hooks import BLOCKED_TOOLS, SINGLE_TOOLS, delegation_tool, single_decision
from scripts.kramabench.native_evidence import claude_delegation_tool, native_single_agent
from scripts.kramabench.run import admission


def test_single_tools_cannot_be_enabled_by_settings_or_permissions(tmp_path):
    adapter = ClaudeCodeSingleAgentCLI()
    command = adapter.command("model", allowed_tools=("Agent", "Bash"),
        settings=dict(disableAllHooks=True, env=dict(CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS="1")))
    settings = json.loads(command[command.index("--settings")+1])
    assert settings["env"]["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] == "0"
    assert settings["disableAllHooks"] is False
    assert set(command[command.index("--tools")+1].split(",")) == set(SINGLE_TOOLS)
    assert set(BLOCKED_TOOLS) <= set(command[command.index("--disallowedTools")+1].split(","))
    assert "--disable-slash-commands" in command
    assert "--strict-mcp-config" in command and "--dangerously-skip-permissions" not in command
    with pytest.raises(ValueError):
        adapter.command("model", isolated_settings=False)


@pytest.mark.parametrize("name", [*BLOCKED_TOOLS, "custom_subagent", "Bash", "TaskOutput", "TaskCreate"])
def test_permission_guard_and_independent_reader_agree(name):
    assert delegation_tool(name) == claude_delegation_tool(name)
    value = single_decision(dict(hook_event_name="PreToolUse", tool_name=name))
    if delegation_tool(name):
        assert value["hookSpecificOutput"]["permissionDecision"] == "deny"
    else:
        assert value == {}


def fixture(root):
    folder = root/"task/claude-code-single-agent"
    work = folder/"workspace"
    work.mkdir(parents=True)
    (work/"pipeline.py").write_text("print(1)")
    (work/"submission.json").write_text(json.dumps(dict(answer=1, pipeline_path="pipeline.py", evidence="fixture", unfinished=[])))
    events = folder/"native-profile/observer/events.jsonl"
    events.parent.mkdir(parents=True)
    rows = [dict(hook_event_name=k, session_id="root", single_agent_policy=True) for k in ("SessionStart", "SessionEnd")]
    events.write_text("\n".join(map(json.dumps, rows)))
    stdout = folder/"cli/stdout.log"
    stdout.parent.mkdir()
    stdout.write_text(json.dumps(dict(type="system", subtype="init", tools=list(SINGLE_TOOLS)))+"\n")
    return folder, events, rows


def test_single_admission_requires_observed_native_policy(tmp_path):
    folder, events, rows = fixture(tmp_path)
    report = dict(task_id="task", backend="claude-code-single-agent", status="cli_exited")
    assert native_single_agent(folder)["passed"]
    assert admission(tmp_path, report)["passed"]
    rows[0].pop("single_agent_policy")
    events.write_text("\n".join(map(json.dumps, rows)))
    assert not admission(tmp_path, report)["passed"]


@pytest.mark.parametrize("violation", ["start", "executed", "member_file", "exposed", "missing_end"])
def test_single_audit_rejects_delegation_or_missing_evidence(tmp_path, violation):
    folder, events, rows = fixture(tmp_path)
    if violation == "start":
        rows.append(dict(hook_event_name="SubagentStart", agent_id="worker", single_agent_policy=True))
    elif violation == "executed":
        rows.append(dict(hook_event_name="PostToolUse", tool_name="Task", single_agent_policy=True))
    elif violation == "member_file":
        path = folder/"native-profile/claude/projects/project/subagents/agent-worker.jsonl"
        path.parent.mkdir(parents=True)
        path.write_text("{}\n")
    elif violation == "exposed":
        (folder/"cli/stdout.log").write_text(json.dumps(dict(type="system", subtype="init", tools=["Agent"])))
    else:
        rows.pop()
    events.write_text("\n".join(map(json.dumps, rows)))
    assert not native_single_agent(folder)["passed"]


def test_single_plan_contains_native_guard_without_side_effects(tmp_path):
    work = tmp_path/"work"
    work.mkdir()
    plan = ClaudeCodeSingleAgentCLI().run("task", model="model", workspace=work, output=tmp_path/"output")
    settings = json.loads(plan["argv"][plan["argv"].index("--settings")+1])
    assert "--single-agent" in settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert not (tmp_path/"output").exists()


def test_recording_hook_only_denies_when_explicitly_single(tmp_path):
    hook = __import__("harness._claude_hooks", fromlist=["x"])
    payload = json.dumps(dict(hook_event_name="PreToolUse", tool_name="Task"))
    for single in (False, True):
        argv = [sys.executable, hook.__file__, "--output", str(tmp_path/(str(single)+".jsonl"))]
        result = subprocess.run(argv+(["--single-agent"] if single else []), input=payload, capture_output=True, text=True, check=True)
        decision = json.loads(result.stdout)
        assert bool(decision) is single
