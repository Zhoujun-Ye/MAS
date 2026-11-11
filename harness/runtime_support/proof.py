"""Validate harness runtime evidence; mocks do not establish benchmark correctness."""

from harness.runtime_support.inference import EFFORTS, configuration

def validate_effort(proof, effort):
    if (effort not in EFFORTS or proof.get('requested_effort') != effort
            or proof.get('request_effort_verified') is not True):
        raise ValueError(f'Matching offline request-effort proof is required for {effort}')
    if (proof.get('inference_policy') != configuration(effort)
            or proof.get('request_configuration_verified') is not True):
        raise ValueError('Matching native thinking/temperature/effort proof is required')


def validate(proof, backend):
    if proof.get('mode') in {'full','observations','full-prompt-only'} or proof.get('evidence_configuration'):
        raise ValueError('Retired FULL/OBS proofs cannot admit baseline launches')
    if proof.get('proof_kind') == 'native_error_injection':
        raise ValueError('A synthetic error probe cannot admit a solver launch')
    if not (proof.get("passed") is True and proof.get("paid_calls") == 0
            and proof.get("network") == "none"):
        raise ValueError("Missing successful no-network native proof with zero paid calls")
    if proof.get("backend", backend) != backend:
        raise ValueError("Native proof belongs to a different backend")
    if backend == "claude-code-single-agent":
        audit = proof.get("native_single_agent", {})
        valid = (audit.get("passed") and audit.get("subagent_starts") == 0
                 and audit.get("executed_delegation_tools") == 0
                 and proof.get("delegation_rejections_observed", 0) >= 2)
    elif backend == "claude-code-subagents":
        audit = proof.get("native_subagents", {})
        valid = (audit.get("passed") and audit.get("subagent_starts", 0) > 0
                 and audit.get("native_team_configs") == 0 and audit.get("teammate_idle_events") == 0)
    else:
        raise ValueError("This proof validator supports only Single and Subagents")
    if not valid:
        raise ValueError("Native proof lacks the required backend-specific observations")


def validate_runtime(proof, backend, image_id, binary_sha256):
    """Admit only evidence collected with the exact runtime about to execute."""
    if proof.get("backend") != backend:
        raise ValueError("Stale native proof: explicit matching backend is required")
    validate(proof, backend)
    if not image_id or not binary_sha256:
        raise ValueError("Runtime proof binding requires image ID and binary SHA-256")
    expected = dict(image_id=image_id, binary_sha256=binary_sha256)
    if proof.get("runtime_binding") != expected:
        raise ValueError("Stale native proof: image or CLI binary binding differs; regenerate offline proof")
