from types import SimpleNamespace

import pytest

from scripts.common import runtime
from scripts.server.benchmark_matrix import solver_command


@pytest.mark.parametrize("backend", ["claude-code-single-agent", "claude-code-subagents"])
def test_high_is_explicit_global_native_effort(backend, tmp_path, monkeypatch):
    captured = {}
    def create(command, **kwargs):
        captured["command"] = command
        return "fixture-container"
    monkeypatch.setattr(runtime.subprocess, "check_output", create)
    runtime.container(tmp_path, tmp_path, tmp_path, "fixture-image", backend=backend, effort="high")
    assert "CLAUDE_CODE_EFFORT_LEVEL=high" in captured["command"]
    assert "CLAUDE_CODE_EFFORT_LEVEL=max" not in captured["command"]
    assert runtime.native_env(backend)["CLAUDE_CODE_EFFORT_LEVEL"] == "max"
    with pytest.raises(ValueError):
        runtime.native_env(backend, effort="unsupported")


def test_matrix_applies_prompt_only_to_mas_and_high_to_both(tmp_path):
    args = SimpleNamespace(root=tmp_path, proofs=tmp_path, image="fixture", credentials=tmp_path/".env",
                           effort="high", organization_prompt=tmp_path/"lead.txt")
    for backend in ("claude-code-single-agent", "claude-code-subagents"):
        command = solver_command(args, "kramabench", SimpleNamespace(id="fixture"), backend, tmp_path/"out")
        assert command[command.index("--effort")+1] == "high"
        assert ("--organization-prompt" in command) == backend.endswith("subagents")
