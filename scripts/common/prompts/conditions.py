"""Select unchanged baseline prompts or an explicitly supplied study override."""

import hashlib

from .single_agent import PROMPT as SINGLE_AGENT_PROMPT
from .structured_subagents import PROMPT as STRUCTURED_SUBAGENTS_PROMPT


def backend_instructions(backend):
    if backend == "claude-code-single-agent":
        return SINGLE_AGENT_PROMPT
    if backend == "claude-code-subagents":
        return STRUCTURED_SUBAGENTS_PROMPT
    raise ValueError("Unsupported backend: " + backend)


def organization_override(path, backend):
    if path is None:
        return None
    if backend != "claude-code-subagents":
        raise ValueError("Organization prompt overrides are only supported for Subagents studies")
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 32768:
        raise ValueError("Organization prompt must be a regular file of at most 32768 bytes")
    raw = path.read_bytes()
    text = raw.decode("utf-8").strip()
    if not text:
        raise ValueError("Organization prompt must not be empty")
    return dict(path=str(path.resolve()), sha256=hashlib.sha256(raw).hexdigest(), text=text)


def condition_instructions(args, backend):
    if getattr(args,'evidence_mode',None):
        if backend!='claude-code-subagents' or getattr(args,'organization_override',None):
            raise ValueError('Evidence mode cannot be combined with Single or an organization override')
        return ''  # Explicit evidence studies use native organization plus their tool protocol.
    override = getattr(args, "organization_override", None)
    if override is not None:
        if backend != "claude-code-subagents":
            raise ValueError("Organization prompt overrides are only supported for Subagents studies")
        return override["text"]
    return backend_instructions(backend)
