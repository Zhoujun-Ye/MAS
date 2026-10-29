"""Frozen τ²-bench prompts (guide §3.4).

BASE is shared by every agent of every condition and follows τ²'s own agent
instruction; role and relay texts were fixed before any run.
"""

from __future__ import annotations

from ..relay import CONDITIONS, STRUCTURED_SCHEMA

BASE = (
    "You are part of a customer service system that helps the user according to the "
    "<policy> provided below. Try to be helpful and always follow the policy. Always make "
    "sure you generate valid JSON only."
)

TURN_RULE = (
    "In each turn you can either send a message to the user or make tool calls. "
    "You cannot do both at the same time."
)

SINGLE = "You talk with the user and you have the customer database tools. " + TURN_RULE

FRONT = (
    "You are the front-desk agent. You talk with the user, but you have no database tools. "
    "To look up or change anything in the customer database, send a request with "
    "delegate(request) to the operator, who has the database tools and the same policy but "
    "cannot talk to the user. " + TURN_RULE
)

OPERATOR = (
    "You are the operator. You cannot talk to the user; you carry out requests from the "
    "front-desk agent, who talks with the user. Use the database tools to complete each "
    "request according to the policy."
)

FRONT_RELAY = {
    "free_text": "The operator sees only your requests. Each delegate call returns the operator's free-text report.",
    "structured": "The operator sees only your requests. Each delegate call returns the operator's report as a JSON object with the fields conclusion, key_facts, ruled_out, open_questions and confidence.",
    "full": "The operator sees the conversation with the user, your working notes so far and your request. Each delegate call returns the operator's report followed by the complete log of its tool calls and their outputs.",
    "reference": "The operator sees only your requests. Its tool outputs and notes are saved to shared storage as artifacts. Each delegate call returns a short summary report and an index of the operator's new artifacts; open any artifact with read_artifact.",
}

OPERATOR_RELAY = {
    "free_text": "When a request is done, reply with a report for the front desk. The front desk sees only this report.",
    "structured": "When a request is done, reply with only a JSON object of the following form. The front desk sees only this JSON.\n" + STRUCTURED_SCHEMA,
    "full": "When a request is done, reply with a report for the front desk. The front desk also receives the complete log of your tool calls and their outputs.",
    "reference": "Each tool output you receive is saved to shared storage as an artifact whose id is on its first line, e.g. [artifact a7]. You can save notes with write_artifact and open any artifact with read_artifact. When a request is done, reply with a short summary report that cites artifact ids. The front desk sees this summary and an index of your new artifacts, and can open them on demand.",
}

TURN_LIMIT_USER = "[System notice] You have reached the turn limit. Send your message to the user now, without calling tools."
TURN_LIMIT_REPORT = "[System notice] You have reached the turn limit. Write your report now, without calling tools."

DELEGATE = {
    "type": "function",
    "function": {
        "name": "delegate",
        "description": "Send a request to the operator, who has the customer database tools, and wait for the operator's report.",
        "parameters": {
            "type": "object",
            "properties": {
                "request": {
                    "type": "string",
                    "description": "What the operator should look up or do, with every detail it needs.",
                }
            },
            "required": ["request"],
        },
    },
}


def system_prompt(role: str, relay: str | None, policy: str) -> str:
    if role == "single":
        instructions = [BASE, SINGLE]
    elif role == "front":
        instructions = [BASE, FRONT, FRONT_RELAY[relay]]
    elif role == "operator":
        instructions = [BASE, OPERATOR, OPERATOR_RELAY[relay]]
    else:
        raise ValueError(f"Unknown role: {role}")
    body = "\n\n".join(instructions)
    return f"<instructions>\n{body}\n</instructions>\n<policy>\n{policy}\n</policy>"


def frozen_prompts() -> dict:
    """Instructions of every role in every condition, with a policy placeholder."""
    prompts = {}
    for condition, (structure, relay) in CONDITIONS.items():
        if structure == "single":
            prompts[condition] = {"single": system_prompt("single", None, "{policy}")}
        elif structure == "team":
            prompts[condition] = {
                role: system_prompt(role, relay, "{policy}") for role in ("front", "operator")
            }
    return prompts
