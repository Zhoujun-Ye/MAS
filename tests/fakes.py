"""Offline stand-ins: a scripted chat client and a three-document corpus."""

from __future__ import annotations

import itertools
import json
import re
import threading

from harness.llm import Completion, ModelConfig, check_reasoning_passback, normalize_usage

DOCS = {
    "101": "The Alpha Prize is awarded every year to an outstanding chemist. It was founded in 1987.",
    "102": "Maria Lopez won the Alpha Prize in 2003 for her work on catalysis.",
    "103": "Unrelated text about rivers and mountains in Bolivia.",
}
TASK = {"query_id": "7", "query": "Who won the Alpha Prize in 2003?", "answer": "Maria Lopez"}
EVIDENCE, GOLD = ["101", "102"], ["102"]


class FakeRetriever:
    def search(self, query: str, k: int) -> list[dict]:
        words = set(re.findall(r"\w+", query.lower()))
        scored = sorted(
            ((len(words & set(re.findall(r"\w+", text.lower()))), docid) for docid, text in DOCS.items()),
            key=lambda item: (-item[0], item[1]),
        )
        return [{"docid": d, "score": float(s), "text": DOCS[d]} for s, d in scored[:k] if s > 0]

    def get_document(self, docid: str) -> dict | None:
        return {"docid": docid, "text": DOCS[docid]} if docid in DOCS else None

    def search_ids(self, query, k):
        return [{key: hit[key] for key in ('docid', 'score')} for hit in self.search(query, k)]


ROLES = (
    ("You are the coordinator of a general-purpose", "lead"),
    ("You are a worker in a general-purpose", "worker"),
    ("You are the lead researcher", "lead"),
    ("You are a search agent", "worker"),
    ("sub-tasks that you will receive", "sequential"),
    ("You work alone", "single"),
    ("You are the front-desk agent", "front"),
    ("You are the operator", "operator"),
    ("you have the customer database tools", "single"),
)


def role_of(messages: list[dict]) -> str:
    return next(role for marker, role in ROLES if marker in messages[0]["content"])


def last_user(messages: list[dict]) -> str:
    return next(m["content"] for m in reversed(messages) if m["role"] == "user")


def turn(messages: list[dict]) -> int:
    """Assistant replies since the latest user message."""
    start = max(i for i, m in enumerate(messages) if m["role"] == "user")
    return sum(m["role"] == "assistant" for m in messages[start:])


class ScriptedClient:
    """Replies from ``policy(messages, tool_names, tool_choice)``.

    Like DeepSeek in thinking mode, it rejects a request with tools whose
    history has an assistant turn without ``reasoning_content``.
    """

    def __init__(self, policy):
        self.cfg = ModelConfig(model="scripted")
        self.policy = policy
        self.requests: list[tuple[list[dict], list[str], str | None]] = []
        self.efforts: list[str | None] = []
        self.response_formats: list[dict | None] = []
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def complete(self, messages, tools=None, tool_choice=None, effort=None, *, response_format=None) -> Completion:
        if tools:
            check_reasoning_passback(messages)
        names = [tool["function"]["name"] for tool in tools or []]
        with self._lock:
            self.requests.append(([dict(m) for m in messages], names, tool_choice))
            self.efforts.append(effort)
            self.response_formats.append(dict(response_format) if response_format is not None else None)
        reply = self.policy(messages, names, tool_choice)
        message = {
            "role": "assistant",
            "content": reply.get("content", ""),
            "reasoning_content": reply.get("reasoning", "thinking"),
        }
        calls = reply.get("calls") or []
        if calls:
            with self._lock:
                ids = [next(self._ids) for _ in calls]
            message["tool_calls"] = [
                {"id": f"call_{i}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
                for i, (name, args) in zip(ids, calls)
            ]
        usage = normalize_usage({"prompt_tokens": 100 * len(messages), "completion_tokens": 10, "prompt_cache_hit_tokens": 40})
        finish = reply.get("finish") or ("tool_calls" if calls else "stop")
        return Completion(message, finish, usage, 0.0, "scripted")
