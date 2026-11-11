"""Retired runtimes and decision gates cannot silently become active baselines."""

from scripts.common.prompts.conditions import backend_instructions, condition_instructions

import json

import pytest

import harness
from harness.__main__ import main
from harness.runtime_support.runtime import (native_env, options)
from scripts.common import grading, score
from scripts.kramabench.cli_runtime import collect_attempt
from types import SimpleNamespace


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


def test_active_scoring_rejects_retired_plans_before_evaluator_or_provider_access(tmp_path, monkeypatch):
    run = tmp_path / 'retired'; run.mkdir()
    (run / 'plan.json').write_text(json.dumps(dict(evidence={'mode': 'full'})))
    monkeypatch.setattr(score.subprocess, 'check_output', lambda *a, **kw: pytest.fail('Retired plan accessed evaluator'))
    with pytest.raises(ValueError, match='read-only'):
        score.main(['--run', str(run), '--upstream', str(tmp_path/'upstream'), '--output', str(tmp_path/'grades')])
    assert not (tmp_path/'grades').exists()


def test_active_krama_paths_do_not_reconstruct_retired_gate_scores(tmp_path):
    record = dict(decision_gate={'accepted': True})
    (tmp_path/'summary.json').write_text(json.dumps(dict(rows=[record])))
    with pytest.raises(ValueError, match='read-only'):
        grading.grade_attempt('kramabench', SimpleNamespace(id='fixture'), 'claude-code-subagents', tmp_path,
            data_root=tmp_path, grades_root=tmp_path/'grades', credentials=None, judge_enabled=True,
            key=None, command_run=None, log=None)
    with pytest.raises(ValueError, match='read-only'):
        collect_attempt(tmp_path, record, None)
    assert not (tmp_path/'grades').exists()


@pytest.mark.parametrize('mode', ('full', 'observations', 'full-prompt-only'))
def test_direct_condition_api_rejects_retired_modes(mode):
    with pytest.raises(ValueError, match='retired|Retired'):
        condition_instructions(SimpleNamespace(evidence_mode=mode), 'claude-code-subagents')
