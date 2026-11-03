"""Read-only compatibility for immutable retired scheduler and Team traces."""

import json
from pathlib import Path

TEXT_FIELDS = {"tool_call": "observation", "boundary_msg": "content"}
USAGE_KEYS = ("prompt_tokens", "completion_tokens", "cache_hit_tokens",
              "cache_miss_tokens", "reasoning_tokens")


def read_trace(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def _resolve(by_t: dict[int, dict], message: dict) -> dict:
    content = message.get("content")
    if isinstance(content, dict) and "$ref" in content:
        source = by_t[content["$ref"]]
        message = dict(message, content=source[TEXT_FIELDS[source["type"]]])
    return message


def contexts(events: list[dict], upto: int | None = None) -> dict[str, list[dict]]:
    """Every agent's message history with references resolved, up to clock ``upto``."""
    by_t = {event["t"]: event for event in events}
    histories: dict[str, list[dict]] = {}
    for event in events:
        if upto is not None and event["t"] > upto:
            break
        if event["type"] == "message":
            histories.setdefault(event["agent"], []).append(_resolve(by_t, event["message"]))
    return histories


def usage_summary(events: list[dict]) -> dict:
    """Token totals overall and per agent, plus the largest single context."""

    def empty() -> dict:
        return {"llm_calls": 0, "attempted_calls": 0, "succeeded_calls": 0, "failed_calls": 0,
                "unknown_usage_calls": 0, "max_prompt_tokens": 0, **{key: 0 for key in USAGE_KEYS}}

    total, agents = empty(), {}
    for event in events:
        if event["type"] not in {"llm_attempt", "llm_call", "llm_error"}:
            continue
        for bucket in (total, agents.setdefault(event["agent"], empty())):
            kind = event["type"]
            if kind == "llm_attempt" or kind == "llm_call" and "attempt_id" not in event:
                bucket["llm_calls"] += 1
                bucket["attempted_calls"] += 1
                bucket["unknown_usage_calls"] += 1
            if kind == "llm_error":
                bucket["failed_calls"] += 1
            if kind != "llm_call":
                continue
            bucket["succeeded_calls"] += 1
            if not event.get("usage_available", True):
                continue
            bucket["unknown_usage_calls"] -= 1
            for key in USAGE_KEYS:
                bucket[key] += event["usage"].get(key, 0)
            bucket["max_prompt_tokens"] = max(
                bucket["max_prompt_tokens"], event["usage"].get("prompt_tokens", 0)
            )
    for bucket in (total, *agents.values()):
        bucket["usage_complete"] = bucket["unknown_usage_calls"] == 0
    return {"total": total, "agents": agents}


def tool_counts(events: list[dict]) -> dict[str, int]:
    """Calls per tool; calls refused because the shared budget ran out are counted apart."""
    counts: dict[str, int] = {}
    for event in events:
        if event["type"] == "tool_call":
            key = "refused_over_budget" if event.get("budget_exhausted") else event["tool"]
            counts[key] = counts.get(key, 0) + 1
    return counts


def communication_summary(events):
    """Intended-recipient mailbox exposure, not semantic use or all information flow.

    Leader inspection through read_messages is a separate, fully logged tool path.
    """
    messages = {e["message_id"]: e for e in events if e["type"] == "team_message"}
    deliveries = {(e["message_id"], e["recipient"]): e for e in events if e["type"] == "team_message_delivery"}
    undelivered = {(e["message_id"], e["recipient"]) for e in events if e["type"] == "team_message_undelivered"}
    routes = []
    for key, message in messages.items():
        for recipient in message["recipients"]:
            delivery = deliveries.get((key, recipient))
            exposed = bool(delivery and any(e["type"] == "llm_attempt" and e["agent"] == recipient and
                e["t"] > delivery["t"] and e["context_len"] > delivery["context_index"] for e in events))
            routes.append(dict(message_id=key, sender=message["sender"], recipient=recipient,
                kind=message["kind"], control=message["control"], queued=True,
                delivered=bool(delivery), exposed=exposed, undelivered=(key, recipient) in undelivered))
    peers = [r for r in routes if r["sender"].startswith("worker-") and r["recipient"].startswith("worker-")]
    return dict(messages=len(messages), explicit_messages=sum(not m["control"] for m in messages.values()),
                peer_routes=len(peers), peer_exposed=sum(r["exposed"] for r in peers), routes=routes)


def validate(events: list[dict], require_reasoning: bool = True) -> list[str]:
    """Gaps that make a run's log incomplete or show broken reasoning passback."""
    problems = []
    kinds = [event["type"] for event in events]
    if not kinds or kinds[0] != "run_start":
        problems.append("first event is not run_start")
    end = next((event for event in events if event["type"] == "run_end"), None)
    if end is None:
        problems.append("no run_end")
    elif end["status"] == "completed" and "final" not in kinds:
        problems.append("completed without a final event")
    logged: dict[str, int] = {}
    for event in events:
        agent = event.get("agent")
        if event["type"] == "message":
            if event["idx"] != logged.get(agent, 0):
                problems.append(f"{agent}: message index gap at t={event['t']}")
            logged[agent] = event["idx"] + 1
        elif event["type"] in {"llm_call", "llm_attempt"} and event["context_len"] > logged.get(agent, 0):
            problems.append(f"{agent}: llm_call at t={event['t']} sent unlogged messages")
    for agent, history in contexts(events).items():
        open_calls: set[str] = set()
        for message in history:
            if message["role"] == "assistant":
                if open_calls:
                    problems.append(f"{agent}: unanswered tool calls {sorted(open_calls)}")
                if require_reasoning and "reasoning_content" not in message:
                    problems.append(f"{agent}: assistant message without reasoning_content")
                open_calls = {call["id"] for call in message.get("tool_calls") or []}
            elif message["role"] == "tool":
                if message["tool_call_id"] not in open_calls:
                    problems.append(f"{agent}: tool result {message['tool_call_id']} without a call")
                open_calls.discard(message["tool_call_id"])
            elif open_calls:
                problems.append(f"{agent}: unanswered tool calls {sorted(open_calls)}")
                open_calls = set()
        if open_calls:
            problems.append(f"{agent}: history ended with unanswered tool calls {sorted(open_calls)}")
    asked = {e["msg_id"] for e in events if e["type"] == "boundary_msg" and e["direction"] == "down"}
    answered = {e.get("reply_to") for e in events if e["type"] == "boundary_msg" and e["direction"] == "up"}
    if end is not None and end["status"] == "completed" and asked - answered:
        problems.append(f"boundary messages without a reply: {sorted(asked - answered)}")
    histories = contexts(events)
    records = {e["message_id"]: e for e in events if e["type"] == "team_message"}
    seen = set()
    for event in events:
        if event["type"] != "team_message_delivery":
            continue
        key = (event["message_id"], event["recipient"])
        record = records.get(key[0])
        history = histories.get(key[1], [])
        index = event["context_index"]
        if key in seen or not record or key[1] not in record["recipients"] or record["t"] >= event["t"]:
            problems.append(f"Invalid or duplicate mailbox delivery: {key}")
        elif index >= len(history) or key[0] not in str(history[index].get("content", "")):
            problems.append(f"Mailbox delivery missing from context: {key}")
        seen.add(key)
    if "session_end" in kinds:
        for route in communication_summary(events)["routes"]:
            if not route["delivered"] and not route["undelivered"]:
                problems.append(f"Mailbox route missing final disposition: {route['message_id']} to {route['recipient']}")
    open_activations = set()
    frozen = False
    for event in events:
        if event["type"] == "team_activation_start":
            if frozen or event["agent"] in open_activations:
                problems.append("Overlapping activation or activation after closure")
            open_activations.add(event["agent"])
        elif event["type"] == "team_activation_end":
            open_activations.discard(event["agent_id"])
        elif event["type"] == "team_frozen":
            frozen = True
            if open_activations:
                problems.append("Team frozen with active workers")
    if "session_end" in kinds and open_activations:
        problems.append("Session ended with unclosed worker activations")
    return problems
