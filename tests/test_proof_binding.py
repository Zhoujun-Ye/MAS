from copy import deepcopy

import pytest

from harness.runtime_support.proof import validate, validate_runtime, runtime_configuration
from harness._claude_hooks import SINGLE_TOOLS


def claude_proof():
    return dict(
        backend="claude-code-single-agent", passed=True, paid_calls=0, network="none",
        native_single_agent=dict(passed=True, subagent_starts=0, executed_delegation_tools=0),
        delegation_rejections_observed=2,
        runtime_binding=dict(image_id="sha256:image", binary_sha256="binary-hash"),
        native_surface=dict(tools=list(SINGLE_TOOLS), skills=[], slash_commands=[]),
        runtime_configuration_sha256=runtime_configuration('claude-code-single-agent'),
    )


def test_exact_claude_runtime_binding_passes():
    validate_runtime(claude_proof(), "claude-code-single-agent", "sha256:image", "binary-hash")


@pytest.mark.parametrize("changed", [None, {}, {"image_id": "other", "binary_sha256": "binary-hash"},
    {"image_id": "sha256:image", "binary_sha256": "other"},
    {"image_id": "sha256:image", "binary_sha256": "binary-hash", "unexpected": True}])
def test_missing_or_stale_runtime_binding_is_rejected(changed):
    proof = claude_proof()
    proof["runtime_binding"] = deepcopy(changed)
    with pytest.raises(ValueError, match="Stale native proof"):
        validate_runtime(proof, "claude-code-single-agent", "sha256:image", "binary-hash")


@pytest.mark.parametrize("backend", [None, "claude-code-subagents"])
def test_runtime_admission_requires_explicit_matching_backend(backend):
    proof = claude_proof()
    if backend is None:
        del proof["backend"]
    else:
        proof["backend"] = backend
    with pytest.raises(ValueError, match="explicit matching backend"):
        validate_runtime(proof, "claude-code-single-agent", "sha256:image", "binary-hash")


def test_runtime_binding_does_not_bypass_native_observations():
    proof = claude_proof()
    proof["native_single_agent"]["subagent_starts"] = 1
    with pytest.raises(ValueError, match="backend-specific observations"):
        validate_runtime(proof, "claude-code-single-agent", "sha256:image", "binary-hash")


def test_legacy_validator_remains_compatible_without_runtime_binding():
    proof = claude_proof()
    del proof["runtime_binding"]
    del proof["backend"]
    validate(proof, "claude-code-single-agent")


def test_error_injection_proof_never_admits_paid_launch():
    proof = claude_proof()
    proof['proof_kind'] = 'native_error_injection'
    with pytest.raises(ValueError, match='error probe'):
        validate(proof, 'claude-code-single-agent')
