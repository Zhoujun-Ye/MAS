from copy import deepcopy

import pytest

from scripts.common.proof import validate, validate_runtime


def claude_proof():
    return dict(
        backend="claude-code-single-agent", passed=True, paid_calls=0, network="none",
        native_single_agent=dict(passed=True, subagent_starts=0, executed_delegation_tools=0),
        delegation_rejections_observed=2,
        runtime_binding=dict(image_id="sha256:image", binary_sha256="binary-hash"),
    )


def codex_proof(backend="codex-subagents"):
    proof = claude_proof()
    proof.update(backend=backend, native_codex=dict(passed=True, subagent_starts=0 if backend.endswith("single-agent") else 1),
                 tool_exposure_verified=True, shell_verified=True)
    proof["runtime_binding"]["catalog_sha256"] = "catalog-hash"
    return proof


def test_exact_claude_runtime_binding_passes():
    validate_runtime(claude_proof(), "claude-code-single-agent", "sha256:image", "binary-hash")


@pytest.mark.parametrize("backend", ["codex-single-agent", "codex-subagents"])
def test_exact_codex_runtime_binding_and_shell_pass(backend):
    validate_runtime(codex_proof(backend), backend, "sha256:image", "binary-hash", "catalog-hash")


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


@pytest.mark.parametrize("shell", [None, False, 1])
def test_codex_requires_explicit_shell_success(shell):
    proof = codex_proof()
    proof["shell_verified"] = shell
    with pytest.raises(ValueError, match="shell execution"):
        validate_runtime(proof, "codex-subagents", "sha256:image", "binary-hash", "catalog-hash")


@pytest.mark.parametrize("catalog", [None, "", "changed-catalog"])
def test_codex_requires_matching_catalog(catalog):
    with pytest.raises(ValueError, match="catalog"):
        validate_runtime(codex_proof(), "codex-subagents", "sha256:image", "binary-hash", catalog)


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
