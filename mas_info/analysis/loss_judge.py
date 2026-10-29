"""Loss-type labels from a separate judge model (guide §5.3, appendix B).

For a failed run the judge sees the decider's context at its final decision,
the other agents' contexts up to that moment and the information the decision
needed (reference answer or gold evidence). Labels are diagnostics for P3 and
must be checked against two human annotators on a 50-event sample.
"""

from __future__ import annotations

import json
import re

from ..llm import ChatClient
from ..trace import contexts

# 遗漏 / 失真 / 条件丢失 / 过期 / 意图丢失 / 排除信息丢失 / 错投
LOSS_TYPES = (
    "omission",
    "distortion",
    "condition_loss",
    "staleness",
    "intent_loss",
    "ruled_out_loss",
    "misrouting",
    "none",
)

PROMPT = """You will see:
1) the context of the deciding agent when it made the key decision of a failed run;
2) the contexts of the other agents up to that moment;
3) the information the decision needed (from the reference answer or gold evidence).

Decide:
a. Does the needed information appear in another agent's context? Give its location.
b. Does it appear in the deciding agent's context? If so, does it match the original value?
c. If information was lost, which type: omission (never passed on), distortion (passed on but changed), condition_loss (a value passed on without its premise or qualifier), staleness (an outdated value passed on), intent_loss (a delegated task lacked its goal, constraint or reason), ruled_out_loss (a ruled-out candidate was not passed on), misrouting (the information existed but never reached the agent that needed it), or none.
d. On which edge did the loss happen, and in which direction (down or up)?

Output only JSON: {{"present_elsewhere": bool, "present_in_decider": bool, "loss_type": "...", "edge": "...", "direction": "down|up|none", "evidence": "..."}}

=== Deciding agent ({decider}) context ===
{decider_context}

=== Other agents' contexts ===
{other_contexts}

=== Needed information ===
{needed}"""


def render(messages: list[dict], limit: int) -> str:
    """Numbered messages; an over-long context keeps head and tail and says so."""
    blocks = []
    for index, message in enumerate(messages):
        parts = [f"[{index}] {message['role']}"]
        if message.get("reasoning_content"):
            parts.append(f"(reasoning) {message['reasoning_content']}")
        if message.get("content"):
            parts.append(str(message["content"]))
        for call in message.get("tool_calls") or []:
            parts.append(f"(call {call['function']['name']}) {call['function']['arguments']}")
        blocks.append("\n".join(parts))
    text = "\n\n".join(blocks)
    if len(text) <= limit:
        return text
    half = limit // 2
    return f"{text[:half]}\n[... {len(text) - 2 * half} characters omitted ...]\n{text[-half:]}"


def build_case(events: list[dict], needed: str, limit: int = 150_000) -> dict:
    final = next(event for event in events if event["type"] == "final")
    decider = final["agent"]
    histories = contexts(events, upto=final["t"])
    others = [
        f"--- {agent} ---\n{render(messages, limit)}"
        for agent, messages in histories.items()
        if agent != decider
    ]
    return {
        "decider": decider,
        "decider_context": render(histories[decider], limit),
        "other_contexts": "\n\n".join(others) or "(no other agents)",
        "needed": needed,
    }


def parse_label(text: str) -> dict | None:
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not match:
        return None
    try:
        label = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(label, dict) or label.get("loss_type") not in LOSS_TYPES:
        return None
    return label


def label(client: ChatClient, case: dict) -> dict:
    completion = client.complete([{"role": "user", "content": PROMPT.format(**case)}])
    text = completion.message.get("content") or ""
    return {
        "label": parse_label(text),
        "judgement": text,
        "judge_model": client.cfg.model,
        "usage": completion.usage,
    }
