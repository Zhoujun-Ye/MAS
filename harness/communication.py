"""Shared handoff forms and structured transport validation."""
import json
import re
from copy import deepcopy


def full_snapshot(messages):
    """Lossless DAG encoding: materialize each upstream frame once, not recursively.

    Frame references replace only previously encoded full-context envelopes;
    every referenced frame is included inline, so no retrieval is necessary.
    """
    from .config import digest
    frames = {}
    current = deepcopy(messages)
    for message in current:
        if message.get("role") != "user":
            continue
        try:
            value = json.loads(message.get("content", ""))
        except (ValueError, TypeError):
            continue
        packet = value.get("incoming_handoff", {}) if isinstance(value, dict) else {}
        payload = packet.get("payload")
        if packet.get("form") == "full_context" and isinstance(payload, dict) and "frames" in payload:
            frames.update(payload["frames"])
            packet["payload"] = {"intent": payload["intent"], "frame_ref": payload["root"]}
            message["content"] = json.dumps(value, ensure_ascii=False)
    root = digest(current)
    frames[root] = current
    return dict(root=root, frames=frames)


def parse_payload(text):
    """Parse a single JSON value, optionally in one Markdown fence.

    Never regex-extract a brace substring or choose between multiple candidates.
    Prose outside a single fence is presentation, not part of the JSON contract.
    """
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        if not isinstance(text, str):
            raise ValueError("JSON text required")
        blocks = re.findall(r"```(?:json)?\s*\n(.*?)\n```", text, flags=re.DOTALL | re.IGNORECASE)
        if len(blocks) != 1 or text.count("```") != 2:
            raise ValueError("Expected exactly one JSON document")
        outside = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        if any(c in outside for c in "{}[]"):
            raise ValueError("Ambiguous JSON outside fence")
        return json.loads(blocks[0])


def normalize_json(text):
    try:
        return json.dumps(parse_payload(text), ensure_ascii=False)
    except (ValueError, TypeError):
        return text


def normalize_record(text):
    """Accept JSON null for the optional verbatim field without altering facts."""
    try:
        record = parse_payload(text)
        for fact in record.get("key_facts", []):
            if isinstance(fact, dict) and fact.get("verbatim", "") is None:
                fact.pop("verbatim")
        return json.dumps(record, ensure_ascii=False)
    except (ValueError, TypeError, AttributeError):
        return text

FORMS = ("full_context", "summary", "structured", "document_retrieval", "adaptive")

STRUCTURED_SCHEMA = """{
  "conclusion": "one-sentence conclusion of this sub-task",
  "key_facts": [{"fact": "...", "source": "docid or tool call id", "verbatim": "exact source excerpt (optional)"}],
  "ruled_out": [{"candidate": "...", "reason": "..."}],
  "open_questions": ["points not yet confirmed"],
  "confidence": "high | medium | low"
}"""

def valid_record(text):
    """Validate the transport contract, not the truth of its assertions."""
    try:
        row = json.loads(text)
    except (ValueError, TypeError):
        return False
    if not isinstance(row, dict) or set(row) != {"conclusion", "key_facts", "ruled_out", "open_questions", "confidence"}:
        return False
    return (isinstance(row["conclusion"], str) and row["confidence"] in ("high", "medium", "low")
            and isinstance(row["key_facts"], list)
            and all(isinstance(f, dict) and {"fact", "source"} <= set(f) <= {"fact", "source", "verbatim"}
                    and all(isinstance(v, str) for v in f.values()) for f in row["key_facts"])
            and isinstance(row["ruled_out"], list)
            and all(isinstance(f, dict) and set(f) == {"candidate", "reason"}
                    and all(isinstance(v, str) for v in f.values()) for f in row["ruled_out"])
            and isinstance(row["open_questions"], list)
            and all(isinstance(q, str) for q in row["open_questions"]))
