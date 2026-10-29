"""Shared handoff forms and structured transport validation."""
import json

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
