"""τ²-bench transmission diagnostics (guide §5.2), mechanical first pass.

- Parameter provenance: for every argument of every gold agent action, where
  the correct value appears (user utterances, front-desk context, acting
  agent's context) and whether an executed call matched the action. A value the
  front desk had but the operator never received, on an unmatched action, is a
  downward-loss candidate.
- Round trips: delegations and repeated identical environment calls.

Constraint coverage and upward contradictions need the judge (a later pass).
"""

from __future__ import annotations

import json
import re

from ..trace import contexts


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text).lower()).strip()


def _text(messages: list[dict]) -> str:
    parts = []
    for message in messages[1:]:
        parts.append(str(message.get("content") or ""))
        for call in message.get("tool_calls") or []:
            parts.append(call["function"]["arguments"])
    return _norm("\n".join(parts))


def _same(expected, actual) -> bool:
    return _norm(json.dumps(expected, sort_keys=True)) == _norm(json.dumps(actual, sort_keys=True))


def analyze(events: list[dict], gold_actions: list[dict]) -> dict:
    histories = contexts(events)
    team = "operator" in histories
    front, actor = ("frontdesk", "operator") if team else ("single", "single")
    user_text = _norm(
        "\n".join(
            message.get("content") or ""
            for message in histories.get(front, [])[1:]
            if message["role"] == "user" and not (message.get("content") or "").startswith("[System notice]")
        )
    )
    front_text, actor_text = _text(histories.get(front, [])), _text(histories.get(actor, []))
    succeeded = [
        event
        for event in events
        if event["type"] == "tool_call"
        and event["tool"] not in ("delegate", "read_artifact", "write_artifact")
        and not event.get("error")
        and not event.get("budget_exhausted")
    ]
    executed = [(event["tool"], event.get("args") or {}) for event in succeeded if event["agent"] == actor]
    params = []
    for action in gold_actions:
        if action.get("requestor", "assistant") != "assistant":
            continue
        args = action.get("arguments") or {}
        keys = action.get("compare_args") or list(args)
        matched = any(
            tool == action["name"] and all(_same(args.get(key), got.get(key)) for key in keys)
            for tool, got in executed
        )
        for key in keys:
            raw = args.get(key)
            value = _norm(raw if isinstance(raw, str) else json.dumps(raw))
            in_front, in_actor = value in front_text, value in actor_text
            params.append(
                {
                    "action": action["name"],
                    "arg": key,
                    "value": raw,
                    "matched": matched,
                    "in_user": value in user_text,
                    "in_front": in_front,
                    "in_actor": in_actor,
                    "down_loss_candidate": team and not matched and in_front and not in_actor,
                }
            )
    calls = [(event["tool"], json.dumps(event.get("args"), sort_keys=True)) for event in succeeded]
    return {
        "team": team,
        "delegations": sum(
            1 for event in events if event["type"] == "boundary_msg" and event["direction"] == "down"
        ),
        "env_calls": len(calls),
        "repeated_calls": len(calls) - len(set(calls)),
        "params": params,
        "down_loss_candidates": sum(row["down_loss_candidate"] for row in params),
    }
