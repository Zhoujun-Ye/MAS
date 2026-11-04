"""Validate native-mode evidence; mock model success is not benchmark correctness."""


def validate(proof, backend):
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
    elif backend in {"codex-single-agent", "codex-subagents"}:
        audit = proof.get("native_codex", {})
        valid = (audit.get("passed") and proof.get("tool_exposure_verified") is True
                 and (audit.get("subagent_starts") == 0 if backend.endswith("single-agent")
                      else audit.get("subagent_starts", 0) > 0))
    else:
        raise ValueError("This proof validator supports only Single and Subagents")
    if not valid:
        raise ValueError("Native proof lacks the required backend-specific observations")


def validate_runtime(proof, backend, image_id, binary_sha256, catalog_sha256=None):
    """Admit only evidence collected with the exact runtime about to execute."""
    if proof.get("backend") != backend:
        raise ValueError("Stale native proof: explicit matching backend is required")
    validate(proof, backend)
    if not image_id or not binary_sha256:
        raise ValueError("Runtime proof binding requires image ID and binary SHA-256")
    expected = dict(image_id=image_id, binary_sha256=binary_sha256)
    if catalog_sha256 is not None:
        expected["catalog_sha256"] = catalog_sha256
    if backend.startswith("codex-"):
        if not catalog_sha256:
            raise ValueError("Codex runtime proof binding requires catalog SHA-256")
        if proof.get("shell_verified") is not True:
            raise ValueError("Stale native proof: Codex shell execution was not verified")
    if proof.get("runtime_binding") != expected:
        raise ValueError("Stale native proof: image, CLI binary or model catalog binding differs; regenerate offline proof")
