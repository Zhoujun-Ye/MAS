"""Retired Team launch paths must not silently become Subagents runs."""

from scripts.common.prompts.conditions import backend_instructions

import json

import pytest

import harness
from harness.__main__ import main
from harness.runtime_support.runtime import (native_env, options)


def test_team_is_not_exported_or_launchable():
    assert not hasattr(harness, "ClaudeCodeAgentTeamCLI")
    with pytest.raises(SystemExit) as error:
        main(["claude-code-agent-team"])
    assert error.value.code == 2


@pytest.mark.parametrize("backend", ["claude-code-agent-team", "codex-agent-team", "codex-single-agent", "codex-subagents", "unknown"])
@pytest.mark.parametrize("build", [backend_instructions, native_env, options])
def test_retired_and_unknown_backends_fail_closed(backend, build):
    with pytest.raises(ValueError):
        build(backend)


@pytest.mark.parametrize("adapter", [harness.ClaudeCodeSubagentsCLI, harness.ClaudeCodeSingleAgentCLI])
def test_remaining_claude_modes_cannot_enable_teams(adapter):
    command = adapter().command("model", settings={
        "env": {"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"},
        "teammateMode": "in-process",
    })
    settings = json.loads(command[command.index("--settings") + 1])
    assert settings["env"]["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] == "0"
    assert "teammateMode" not in settings
    assert "--print" in command
