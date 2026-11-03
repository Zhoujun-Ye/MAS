import json

import pytest

from harness.deepagents.cli import DeepAgentsCLI
from harness.deepagents.hooks import decision
from harness.deepagents.single import audit_events, prepare_profile, validate_profile


@pytest.mark.parametrize("tool", ["task", "Agent", "Task", "start_async_task", "update_async_task", "cancel_async_task"])
def test_native_single_policy_denies_delegation(tool):
    result = decision(dict(hook_event_name="PreToolUse", tool_name=tool))
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_native_policy_does_not_grant_shell_permissions():
    assert decision(dict(hook_event_name="PreToolUse", tool_name="execute")) == {}


def test_single_profile_is_bound_and_audited(tmp_path):
    profile = tmp_path / "profile"
    prepare_profile(profile, script="/guard.py", observer="/events.jsonl")
    assert validate_profile(profile)["native_command"].startswith("python3 -I /guard.py")
    events = tmp_path / "events.jsonl"
    events.write_text('\n'.join(json.dumps(dict(hook_event_name=k)) for k in ("SessionStart", "SessionEnd")))
    assert audit_events(events)["passed"]
    with events.open("a") as stream:
        stream.write("\n" + json.dumps(dict(hook_event_name="SubagentStart")))
    assert not audit_events(events)["passed"]
    (profile / "hooks.json").write_text("{}")
    with pytest.raises(ValueError, match="changed"):
        validate_profile(profile)


def test_single_command_closes_interpreter_and_mcp_routes():
    command = DeepAgentsCLI().command("anthropic:deepseek-flash", single_agent=True)
    assert "--no-interpreter" in command and "--no-mcp" in command
    capped = DeepAgentsCLI().command("anthropic:deepseek-flash", single_agent=True, max_turns=500)
    assert capped[-2:] == ["--max-turns", "500"]
