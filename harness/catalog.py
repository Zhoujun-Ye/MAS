"""Serializable frozen capability catalog for run provenance, not prompt mutation."""

from dataclasses import asdict, dataclass
import hashlib
import json


@dataclass(frozen=True)
class CapabilityTemplate:
    name: str
    description: str
    system: str
    tools: tuple[str, ...] = ()
    max_turns: int | None = None
    tool_budget: int | None = None

    def __post_init__(self):
        object.__setattr__(self, "tools", tuple(self.tools))
        if not self.name or (self.max_turns is not None and self.max_turns < 2) or (self.tool_budget is not None and self.tool_budget < 0):
            raise ValueError("Invalid capability template or limits")


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def catalog_manifest(templates, tools):
    templates, tools = tuple(templates), tuple(tools)
    names = {tool.name for tool in tools}
    if len(names) != len(tools) or len({t.name for t in templates}) != len(templates):
        raise ValueError("Duplicate catalog names")
    if any(not set(t.tools) <= names for t in templates):
        raise ValueError("Unregistered template grant")
    payload = {"templates": [asdict(t) for t in templates], "tools": [
        {"name": t.name, "description": t.description, "parameters": t.parameters,
         "budgeted": t.budgeted, "read_only": t.read_only}
        for t in sorted(tools, key=lambda t: t.name)]}
    # Roundtrip also separates the frozen manifest from mutable caller schemas.
    return json.loads(json.dumps(dict(payload, sha256=fingerprint(payload))))
