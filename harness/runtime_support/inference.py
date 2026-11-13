"""Frozen provider parameters sent by the native CLI, never rewritten by the gateway."""

import math

DEFAULT_EFFORT = "none"
DEFAULT_TEMPERATURE = 1.0
EFFORTS = ("none", "high", "max")


def configuration(effort=DEFAULT_EFFORT):
    if effort not in EFFORTS:
        raise ValueError("Inference mode must be none (thinking off), high or max")
    return dict(thinking="disabled" if effort == "none" else "enabled",
                temperature=DEFAULT_TEMPERATURE if effort == "none" else None,
                effort=None if effort == "none" else effort)


def request_configuration(payload):
    thinking = payload.get("thinking")
    config = payload.get("output_config")
    temperature = payload.get("temperature")
    mode = thinking.get("type") if isinstance(thinking, dict) else None
    effort = config.get("effort") if isinstance(config, dict) else None
    top_p = payload.get("top_p")
    return dict(model=payload.get("model"), max_tokens=payload.get("max_tokens") if type(payload.get("max_tokens")) is int else None,
        thinking=mode if mode in (None, "enabled", "disabled", "adaptive") else "unsupported",
        temperature=temperature if type(temperature) in (int, float) and math.isfinite(temperature) else None,
        temperature_present="temperature" in payload,
        top_p=top_p if type(top_p) in (int, float) and math.isfinite(top_p) else None,
        top_p_present="top_p" in payload,
        effort=effort if effort in (None, "low", "medium", "high", "xhigh", "max") else "unsupported")


def matches(payload, expected):
    observed = request_configuration(payload)
    thinking = "enabled" if observed["thinking"] == "adaptive" else observed["thinking"]
    return (thinking == expected["thinking"] and observed["effort"] == expected["effort"]
            and (expected["temperature"] is None or
                 (observed["temperature_present"] and observed["temperature"] == expected["temperature"])))


def proof_requests(requests, effort):
    expected = configuration(effort)
    observed = [request_configuration(r) for r in requests]
    return dict(requested_effort=effort, inference_policy=expected,
        observed_request_efforts=[r['effort'] for r in observed],
        observed_request_max_tokens=sorted({r['max_tokens'] for r in observed if r['max_tokens'] is not None}),
        observed_request_configurations=observed,
        request_effort_verified=bool(observed) and all(r['effort'] == expected['effort'] for r in observed),
        request_configuration_verified=bool(observed) and all(matches(r, expected) for r in requests))
