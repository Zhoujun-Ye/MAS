"""Append-only JSONL run trace (guide §4).

One event per line with a run-local clock ``t``. Every message an agent adds to
its context is logged, so the exact input of any LLM call can be rebuilt. A
message whose text is already stored in another event references that event's
``t`` instead of repeating the text.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

# boundary_msg is read-only compatibility for immutable retired peer-team traces.
TEXT_FIELDS = {"tool_call": "observation", "boundary_msg": "content"}
ID_FIELDS = {"tool_call": ("obs_id", "o")}
USAGE_KEYS = (
    "prompt_tokens",
    "completion_tokens",
    "cache_hit_tokens",
    "cache_miss_tokens",
    "reasoning_tokens",
)


class Trace:
    """Thread-safe writer for one run; never overwrites an existing trace."""

    def __init__(self, path: Path, run_id: str):
        self.path = Path(path)
        self.run_id = run_id
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("x", encoding="utf-8")
        self._lock = threading.Lock()
        self._t = 0

    def emit(self, type: str, **fields) -> int:
        with self._lock:
            t = self._t
            self._t += 1
            ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
            event = {"run_id": self.run_id, "t": t, "type": type, "ts": ts, "monotonic_ns": time.monotonic_ns()}
            if type in ID_FIELDS:
                key, prefix = ID_FIELDS[type]
                event[key] = f"{prefix}{t}"
            event.update(fields)
            self._file.write(json.dumps(event, ensure_ascii=False) + "\n")
            self._file.flush()
        return t

    def close(self) -> None:
        self._file.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


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


def llm_inputs(events: list[dict], agent: str) -> list[list[dict]]:
    """The exact message list sent in each of ``agent``'s LLM calls."""
    history = contexts(events).get(agent, [])
    return [
        history[: event["context_len"]]
        for event in events
        if event.get("agent") == agent and (event["type"] == "llm_attempt" or
            event["type"] == "llm_call" and "attempt_id" not in event)
    ]


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


def activation_summary(events):
    """Separate message-driven domain actions from assigned work, not semantic production labels."""
    rows, active = [], {}
    snapshots, messages, pending_exposure = {}, {}, {}
    leader_domain_actions = []
    for event in events:
        kind = event["type"]
        if kind == "team_message":
            messages[event["message_id"]] = {k: event.get(k) for k in
                ("message_id", "sender", "recipient", "task_id", "specification_revision", "reply_to")}
        elif kind == "team_activation_start":
            row = dict(agent=event["agent"], activation=event["activation"], cause=event["cause"],
                       task_id=event.get("task_id"), previous_task_id=event.get("previous_task_id"),
                       pending_task_id=event.get("pending_task_id"), assignment_revision=event.get("assignment_revision"),
                       write_scope=event.get("write_scope"), start_event=event["t"], end_event=None,
                       trigger_message_ids=event.get("trigger_message_ids", []),
                       trigger_messages=[messages.get(mid, {"message_id": mid}) for mid in event.get("trigger_message_ids", [])],
                       exposed_message_ids=[], domain_actions=[], workspace_changes=None, audit_events={},
                       model_attempts=0, tool_calls=0, domain_tool_calls=0, domain_tools={}, outcome=None,
                       completion_status=None)
            rows.append(row)
            active[event["agent"]] = row
            pending_exposure[event["agent"]] = []
        elif kind == "team_activation_end":
            row = active.pop(event["agent_id"], None)
            if row is not None:
                row["outcome"] = event["outcome"]
                row["completion_status"] = event.get("completion_status")
                row["end_event"] = event["t"]
        elif event.get("agent") in active:
            row = active[event["agent"]]
            if kind == "llm_attempt":
                row["model_attempts"] += 1
                delivered = pending_exposure[event["agent"]]
                row["exposed_message_ids"].extend(e["message_id"] for e in delivered if event["context_len"] > e["context_index"])
                pending_exposure[event["agent"]] = [e for e in delivered if event["context_len"] <= e["context_index"]]
            elif kind == "workspace_snapshot" and event.get("activation") == row["activation"]:
                snapshot = event.get("snapshot")
                phase = event["phase"]
                row["audit_events"][phase] = event["t"]
                if isinstance(snapshot, dict) and isinstance(snapshot.get("files"), dict):
                    key = (row["agent"], row["activation"])
                    if phase == "before":
                        snapshots[key] = snapshot["files"]
                    elif phase == "after" and key in snapshots:
                        before, after = snapshots.pop(key), snapshot["files"]
                        row["workspace_changes"] = [dict(path=p, before=before.get(p), after=after.get(p))
                            for p in sorted(before.keys() | after.keys()) if before.get(p) != after.get(p)]
            elif kind == "tool_call":
                row["tool_calls"] += 1
                if event.get("budget_charged"):
                    row["domain_tool_calls"] += 1
                    name = event["tool"]
                    row["domain_tools"][name] = row["domain_tools"].get(name, 0) + 1
                    row["domain_actions"].append(dict(event=event["t"], call_id=event["call_id"], tool=name,
                        declared_path=(event.get("args") or {}).get("path"), error_kind=event.get("error_kind"), exit_code=event.get("exit_code")))
        if kind == "team_message_delivery" and event.get("recipient") in active:
            pending_exposure[event["recipient"]].append(event)
        if kind == "tool_call" and event.get("agent") == "leader" and event.get("budget_charged"):
            leader_domain_actions.append(dict(event=event["t"], call_id=event["call_id"], tool=event["tool"]))
    totals = {}
    for row in rows:
        group = totals.setdefault(row["cause"], dict(activations=0, model_attempts=0, tool_calls=0, domain_tool_calls=0))
        group["activations"] += 1
        for key in ("model_attempts", "tool_calls", "domain_tool_calls"):
            group[key] += row[key]
    for row in rows:
        row["overlapping_activations"] = [other["activation"] for other in rows if other is not row and
            other["start_event"] < (row["end_event"] or float("inf")) and
            row["start_event"] < (other["end_event"] or float("inf"))]
    return dict(by_cause=totals, activations=rows, leader_domain_tool_calls=len(leader_domain_actions),
                leader_domain_actions=leader_domain_actions,
                interpretation="Execution cause and shared-interval file changes, not semantic production, verified success or exclusive write attribution; null changes means unavailable audit")


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
