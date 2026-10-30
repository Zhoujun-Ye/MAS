"""Agent-team transport identity and JSON parsing for plans/final answers."""
import json
import re

FORMS = ("agent_team",)


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
