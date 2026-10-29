"""Append-only JSONL run trace (guide §4).

One event per line with a run-local clock ``t``. Every message an agent adds to
its context is logged, so the exact input of any LLM call can be rebuilt. A
message whose text is already stored in another event references that event's
``t`` instead of repeating the text.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

# Event field holding the text that a message may reference.
TEXT_FIELDS = {"tool_call": "observation", "boundary_msg": "content"}
ID_FIELDS = {"tool_call": ("obs_id", "o"), "boundary_msg": ("msg_id", "m")}
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
            event = {"run_id": self.run_id, "t": t, "type": type}
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
        if event["type"] == "llm_call" and event["agent"] == agent
    ]


def usage_summary(events: list[dict]) -> dict:
    """Token totals overall and per agent, plus the largest single context."""

    def empty() -> dict:
        return {"llm_calls": 0, "max_prompt_tokens": 0, **{key: 0 for key in USAGE_KEYS}}

    total, agents = empty(), {}
    for event in events:
        if event["type"] != "llm_call":
            continue
        for bucket in (total, agents.setdefault(event["agent"], empty())):
            bucket["llm_calls"] += 1
            for key in USAGE_KEYS:
                bucket[key] += event["usage"].get(key, 0)
            bucket["max_prompt_tokens"] = max(
                bucket["max_prompt_tokens"], event["usage"].get("prompt_tokens", 0)
            )
    return {"total": total, "agents": agents}


def tool_counts(events: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        if event["type"] == "tool_call":
            counts[event["tool"]] = counts.get(event["tool"], 0) + 1
    return counts
