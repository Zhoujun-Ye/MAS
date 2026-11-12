from types import SimpleNamespace

import pytest

from harness.runtime_support import runtime
from scripts.studies.benchmark_matrix import solver_command


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
    assert runtime.native_env(backend)["CLAUDE_CODE_EFFORT_LEVEL"] == "auto"
    with pytest.raises(ValueError):
        runtime.native_env(backend, effort="unsupported")


def test_matrix_applies_prompt_only_to_mas_and_high_to_both(tmp_path):
    args = SimpleNamespace(root=tmp_path, proofs=tmp_path, image="fixture", credentials=tmp_path/".env",
                           effort="high", organization_prompt=tmp_path/"lead.txt")
    for backend in ("claude-code-single-agent", "claude-code-subagents"):
        command = solver_command(args, "kramabench", SimpleNamespace(id="fixture"), backend, tmp_path/"out")
        assert command[command.index("--effort")+1] == "high"
        assert ("--organization-prompt" in command) == backend.endswith("subagents")


def test_default_means_thinking_off_temperature_one_not_max():
    import json
    assert runtime.DEFAULT_EFFORT == 'none'
    env = runtime.native_env('claude-code-subagents')
    assert env['MAX_THINKING_TOKENS'] == '0'
    assert json.loads(env['CLAUDE_CODE_EXTRA_BODY']) == {'thinking': {'type': 'disabled'}, 'temperature': 1.0}
    assert env['PYTHONHASHSEED'] == '0' and env['TZ'] == 'UTC'
    assert runtime.inference_configuration()['effort'] is None


def test_child_default_is_explicitly_forwarded(tmp_path):
    args = SimpleNamespace(root=tmp_path, proofs=tmp_path, image='fixture', credentials=tmp_path/'.env')
    for condition in ('claude-code-single-agent', 'native', 'claude-code-subagents'):
        command = solver_command(args, 'kramabench', SimpleNamespace(id='fixture'), condition, tmp_path/'out')
        assert command[command.index('--effort')+1] == 'none'


def test_thinking_off_admission_needs_a_sampling_proof():
    from harness.runtime_support.proof import validate_effort
    from harness.runtime_support.inference import proof_requests
    proof = proof_requests([dict(model='deepseek-flash', thinking={'type': 'disabled'}, temperature=1.0)], 'none')
    validate_effort(proof, 'none')
    proof['request_configuration_verified'] = False
    with pytest.raises(ValueError, match='thinking/temperature/effort proof'):
        validate_effort(proof, 'none')
