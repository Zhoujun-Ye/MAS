"""The τ² adapter against τ²'s real telecom environment, with a scripted model."""

import json

import pytest
from fakes import ScriptedClient, role_of, turn

pytest.importorskip("tau2")

from tau2.data_model.message import AssistantMessage, MultiToolMessage, UserMessage  # noqa: E402
from tau2.registry import registry  # noqa: E402

from mas_info.tau import diagnostics  # noqa: E402
from mas_info.tau.team import TeamAgent, TeamContext  # noqa: E402
from mas_info.trace import Trace, read_trace  # noqa: E402

PHONE = "555-123-2002"
STRUCTURED = {"conclusion": "Looked up.", "key_facts": [], "ruled_out": [], "open_questions": [], "confidence": "high"}


def policy(messages, tools, tool_choice):
    role, n = role_of(messages), turn(messages)
    if role == "front":
        if n == 0:
            return {"calls": [("delegate", {"request": f"Look up the customer with phone number {PHONE}."})]}
        if n == 1 and "read_artifact" in tools:
            return {"calls": [("read_artifact", {"artifact_id": "a1"})]}
        return {"content": "Thanks, I checked your account."}
    if role == "operator":
        if n == 0:
            return {"calls": [("get_customer_by_phone", {"phone_number": PHONE})]}
        if "only a JSON object" in messages[0]["content"]:
            return {"content": json.dumps(STRUCTURED)}
        return {"content": "Lookup done."}
    if role == "single":
        if n == 0:
            return {"calls": [("get_customer_by_phone", {"phone_number": PHONE})]}
        return {"content": "Thanks, I checked your account."}
    raise AssertionError(role)


def converse(tmp_path, condition, tool_calls=30):
    env = registry.get_env_constructor("telecom")()
    path = tmp_path / f"{condition}.jsonl"
    with Trace(path, f"telecom_q1_{condition}_r0") as trace:
        ctx = TeamContext(condition, ScriptedClient(policy), trace, tool_calls=tool_calls, max_turns=5, max_delegations=3)
        agent = TeamAgent(env.get_tools(), env.get_policy(), ctx)
        state = agent.get_init_state([AssistantMessage(role="assistant", content="Hi! How can I help you today?")])
        reply, state = agent.generate_next_message(UserMessage(role="user", content=f"My number is {PHONE}."), state)
        emitted = 0
        while reply.is_tool_call():
            emitted += len(reply.tool_calls)
            results = [env.get_response(call) for call in reply.tool_calls]
            incoming = results[0] if len(results) == 1 else MultiToolMessage(role="tool", tool_messages=results)
            reply, state = agent.generate_next_message(incoming, state)
    return reply, read_trace(path), agent, emitted


def boundary(events, direction):
    return [e for e in events if e["type"] == "boundary_msg" and e["direction"] == direction]


def test_single_agent_calls_environment_directly(tmp_path):
    reply, events, agent, emitted = converse(tmp_path, "C0")
    assert reply.content == "Thanks, I checked your account." and emitted == 1
    assert agent.budget.used == 1 and not boundary(events, "down")
    call = next(e for e in events if e["type"] == "tool_call")
    assert call["agent"] == "single" and call["tool"] == "get_customer_by_phone"


@pytest.mark.parametrize("condition", ["C1", "C2", "C3", "C4"])
def test_operator_calls_go_through_tau2(tmp_path, condition):
    reply, events, agent, emitted = converse(tmp_path, condition)
    assert reply.content == "Thanks, I checked your account." and emitted == 1
    down, up = boundary(events, "down"), boundary(events, "up")
    assert [e["edge"] for e in down] == ["frontdesk->operator"]
    assert [e["edge"] for e in up] == ["operator->frontdesk"]
    calls = [e for e in events if e["type"] == "tool_call" and e["tool"] == "get_customer_by_phone"]
    assert [e["agent"] for e in calls] == ["operator"] and agent.budget.used == 1
    if condition == "C2":
        assert up[0]["schema_valid"]
    if condition == "C3":
        dialogue = "Original task:\nFront desk: Hi! How can I help you today?\nUser: My number is"
        assert down[0]["content"].startswith(dialogue)
        assert "=== Complete tool log ===" in up[0]["content"]
    if condition == "C4":
        assert calls[0]["observation"].startswith("[artifact a1]")
        assert any(e["tool"] == "read_artifact" and e["agent"] == "frontdesk" for e in events if e["type"] == "tool_call")


def test_budget_stops_environment_calls(tmp_path):
    reply, events, agent, emitted = converse(tmp_path, "C1", tool_calls=0)
    assert emitted == 0 and reply.content == "Thanks, I checked your account."
    assert any(e.get("budget_exhausted") for e in events if e["type"] == "tool_call")


def test_parameter_provenance(tmp_path):
    _, events, _, _ = converse(tmp_path, "C1")
    gold = [{"name": "get_customer_by_phone", "arguments": {"phone_number": PHONE}, "requestor": "assistant"}]
    result = diagnostics.analyze(events, gold)
    assert result["team"] and result["delegations"] == 1
    row = result["params"][0]
    assert row["in_user"] and row["in_front"] and row["in_actor"]
    assert not row["down_loss_candidate"]
