"""Experimental conditions and how information crosses an agent boundary (guide §3.2).

- free_text (C1): the manager sees only the worker's own report.
- structured (C2): the report must follow the fixed schema of guide appendix A.
- full (C3): up, the report plus every tool call and output verbatim; down, the
  original task and the manager's working notes besides the assignment.
- reference (C4): tool outputs and notes go to shared storage; up, a summary plus
  an index of the worker's artifacts, which the manager can open on demand.
"""

from __future__ import annotations

import json
import threading
from dataclasses import replace
from typing import Callable

from .agent import Observation, Tool
from .trace import Trace

# condition -> (structure, relay form)
CONDITIONS = {
    "C0": ("single", None),
    "C1": ("team", "free_text"),
    "C2": ("team", "structured"),
    "C3": ("team", "full"),
    "C4": ("team", "reference"),
    "C5": ("sequential", None),
}

STRUCTURED_SCHEMA = """{
  "conclusion": "one-sentence conclusion of this sub-task",
  "key_facts": [{"fact": "...", "source": "docid or tool call id", "verbatim": "exact source excerpt (optional)"}],
  "ruled_out": [{"candidate": "...", "reason": "..."}],
  "open_questions": ["points not yet confirmed"],
  "confidence": "high | medium | low"
}"""
STRUCTURED_FIELDS = ("conclusion", "key_facts", "ruled_out", "open_questions", "confidence")


def working_notes(messages: list[dict]) -> str:
    """The manager's own reasoning, messages and tool calls so far (C3 downward notes)."""
    parts = []
    for message in messages:
        if message.get("role") != "assistant":
            continue
        if message.get("reasoning_content"):
            parts.append(f"[reasoning]\n{message['reasoning_content']}")
        if message.get("content"):
            parts.append(message["content"])
        for call in message.get("tool_calls") or []:
            parts.append(f"[{call['function']['name']}] {call['function']['arguments']}")
    return "\n\n".join(parts) or "(none yet)"


def brief(relay: str, assignment: str, *, original: str, notes: str | None) -> str:
    """The downward message exactly as the worker receives it."""
    if relay != "full":
        return assignment
    return (
        f"Original task:\n{original}\n\n"
        f"Manager's working notes so far:\n{notes}\n\n"
        f"Your assignment:\n{assignment}"
    )


def tool_log(messages: list[dict], refs: list[int | None]) -> str:
    """Every tool call in ``messages`` with its verbatim output (C3 upward attachment)."""
    outputs = {
        message["tool_call_id"]: (message["content"], ref)
        for message, ref in zip(messages, refs)
        if message.get("role") == "tool"
    }
    entries = []
    for message in messages:
        if message.get("role") != "assistant":
            continue
        for call in message.get("tool_calls") or []:
            output, ref = outputs.get(call["id"], ("(no output)", None))
            label = f"o{ref}" if ref is not None else call["id"]
            function = call["function"]
            entries.append(f"[{label}] {function['name']}({function['arguments']})\n{output}")
    return "\n\n".join(entries) or "(no tool calls)"


def parse_structured(report: str) -> dict | None:
    """The C2 report as a dict, or None when it does not follow the schema."""
    text = report.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(value, dict) or not set(STRUCTURED_FIELDS) <= set(value):
        return None
    return value


def deliver(relay: str, report: str, attachment: str | None) -> str:
    """The upward message exactly as the manager receives it."""
    if relay == "full":
        return f"{report}\n\n=== Complete tool log ===\n{attachment}"
    if relay == "reference":
        return f"{report}\n\n=== Artifact index ===\n{attachment}"
    return report


class ArtifactStore:
    """Shared storage of condition C4. Ids a1, a2, ... follow creation order."""

    def __init__(self, trace: Trace):
        self.trace = trace
        self._items: dict[str, dict] = {}
        self._lock = threading.Lock()

    def count(self) -> int:
        return len(self._items)

    def put(self, author: str, kind: str, label: str, text: str) -> str:
        with self._lock:
            artifact_id = f"a{len(self._items) + 1}"
            self._items[artifact_id] = {"author": author, "kind": kind, "label": label, "text": text}
        self.trace.emit(
            "artifact_write", artifact_id=artifact_id, author=author, kind=kind, label=label, text=text
        )
        return artifact_id

    def index(self, author: str, after: int = 0) -> str:
        """Artifacts that ``author`` created after the first ``after`` artifacts."""
        with self._lock:
            items = list(self._items.items())
        lines = [
            f"[{artifact_id}] {item['kind']}: {item['label']} ({len(item['text'])} chars)"
            for number, (artifact_id, item) in enumerate(items, start=1)
            if number > after and item["author"] == author
        ]
        return "\n".join(lines) or "(no artifacts)"

    def saving(self, tool: Tool, label: Callable[[dict], str]) -> Tool:
        """Wrap a tool so each output is stored and shown with its artifact id."""

        def run(args: dict, agent) -> Observation:
            obs = tool.run(args, agent)
            artifact_id = self.put(agent.name, tool.name, label(args), obs.text)
            return Observation(f"[artifact {artifact_id}]\n{obs.text}", {**obs.meta, "artifact_id": artifact_id})

        return replace(tool, run=run)

    def write_tool(self) -> Tool:
        def run(args: dict, agent) -> Observation:
            artifact_id = self.put(agent.name, "note", str(args["title"]), str(args["content"]))
            return Observation(f"Saved as artifact {artifact_id}.", {"artifact_id": artifact_id})

        return Tool(
            "write_artifact",
            "Save a note to shared storage and return its artifact id.",
            {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Short title of the note."},
                    "content": {"type": "string", "description": "Text of the note."},
                },
                "required": ["title", "content"],
            },
            run,
        )

    def read_tool(self) -> Tool:
        def run(args: dict, agent) -> Observation:
            artifact_id = str(args["artifact_id"]).strip("[] ")
            item = self._items.get(artifact_id)
            if item is None:
                return Observation(f"Unknown artifact: {artifact_id}", {"error": True})
            return Observation(item["text"], {"artifact_id": artifact_id})

        return Tool(
            "read_artifact",
            "Open an artifact from shared storage by its id.",
            {
                "type": "object",
                "properties": {
                    "artifact_id": {"type": "string", "description": "Artifact id, e.g. a12."}
                },
                "required": ["artifact_id"],
            },
            run,
        )
