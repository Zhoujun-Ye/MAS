import json

import pytest

from fakes import ScriptedClient
from harness.agent import Observation, Tool
from harness.agent_team import AgentTeam
from harness.communication import FORMS
from harness.pool import POOL, Member, TeamSpec, bind_permissions, select_team
from harness.trace import Trace, read_trace, validate


def encoded(messages, content="Available; verify warehouse qualifier."):
    instruction = json.loads(messages[-1]["content"])["handoff_instruction"]
    if "schema" in instruction:
        content = json.dumps(dict(conclusion=content, key_facts=[], ruled_out=[], open_questions=[], confidence="low"))
    return {"content": content}


def policy(messages, tools, choice):
    if choice == "none":
        return encoded(messages)
    role = messages[0]["content"].split("Reusable role: ")[1].split(".")[0]
    count = sum(m["role"] == "assistant" for m in messages)
    if role == "researcher" and count == 0:
        return {"calls": [("stock", {})]}
    if role == "researcher" and count == 1:
        return {"calls": [("send_message", {"recipient": "reviewer", "content": "Check warehouse B only.", "evidence_ids": ["e1"]})]}
    return {"content": "Verified final" if role == "leader" else "Current work complete."}


def build(tmp_path, form, client=None, **limits):
    task = "Deliver only to warehouse A."
    spec = select_team(task, {"researcher": "Read inventory", "reviewer": "Verify warehouse", "leader": "Decide"})
    trace = Trace(tmp_path / f"{form}.jsonl", form)
    trace.emit("run_start")
    tool = Tool("stock", "Read stock", {"type": "object", "properties": {}},
                lambda args, agent: Observation("5 units, warehouse B only."))
    team = AgentTeam(spec, form, client or ScriptedClient(policy), trace, [tool],
                     {"researcher": ["stock"], "reviewer": [], "leader": []}, **limits)
    return task, team, trace


def test_five_forms_freeze_controls_and_peer_delivery(tmp_path):
    digests = set()
    for form in FORMS:
        task, team, trace = build(tmp_path, form)
        result = team.run_task(task)
        trace.emit("run_end", status=result["status"])
        trace.close()
        assert result["status"] == "completed"
        digests.add(team.control_digest)
        events = read_trace(trace.path)
        assert validate(events) == []
        assert any(e["type"] == "peer_delivery" and e["sender"] == "researcher" and e["recipient"] == "reviewer" for e in events)
        assert team.budget.used == 1
        assert all(task in a.messages[1]["content"] for a in team.agents.values())
        assert "stock" not in team.agents["reviewer"].tools
        if form == "full_context":
            assert "warehouse B only" in str(team.agents["reviewer"].messages)
        with pytest.raises(ValueError):
            team.run_task(task)
    assert len(digests) == 1


def test_acl_and_retrieval_not_a_global_notebook(tmp_path):
    task, team, trace = build(tmp_path, "document_retrieval")
    team.run_task(task)
    reviewer = team.agents["reviewer"]
    read = reviewer.tools["read_evidence"].run
    assert "warehouse B only" in read({"id": "e1"}, reviewer).text
    assert "not granted" in read({"id": "e999"}, reviewer).text
    with pytest.raises(ValueError):
        team.queue("reviewer", "leader", "Invented ref", ["e999"])
    trace.close()


def test_summary_cannot_open_reference_backdoor(tmp_path):
    task, team, trace = build(tmp_path, "summary")
    team.run_task(task)
    reviewer = team.agents["reviewer"]
    assert "disabled" in reviewer.tools["read_evidence"].run({"id": "e1"}, reviewer).text
    assert "e1" not in team.access["reviewer"]
    trace.close()


def test_call_and_message_caps_include_encoders(tmp_path):
    task, team, trace = build(tmp_path, "summary", max_calls=3)
    result = team.run_task(task)
    assert result["status"] == "incomplete" and result["reason"] == "model_call_limit"
    assert team.calls == 3
    trace.close()


def test_message_limit_is_not_swallowed_as_a_success(tmp_path):
    task, team, trace = build(tmp_path, "summary", max_messages=1)
    result = team.run_task(task)
    assert result["status"] == "incomplete" and result["reason"] == "message_limit"
    trace.close()


def test_capability_binding_does_not_grant_execution_to_reviewer():
    spec = select_team("check", {"executor": "Act", "reviewer": "Verify", "leader": "Summarize"})
    permissions = bind_permissions(spec, {"inspect": "read", "mutate": "execute"})
    assert permissions["reviewer"] == ("inspect",)
    assert permissions["executor"] == ("inspect", "mutate")


def test_context_overflow_is_incomplete_without_truncation(tmp_path):
    task, team, trace = build(tmp_path, "full_context", max_input_chars=1)
    result = team.run_task(task)
    assert result["status"] == "incomplete" and result["reason"] == "context_length"
    assert task in team.agents["researcher"].messages[1]["content"]
    trace.close()


def test_bad_structured_encoder_is_not_a_scored_failure(tmp_path):
    def bad(messages, tools, choice):
        return {"content": "not a structured record"} if choice == "none" else policy(messages, tools, choice)
    task, team, trace = build(tmp_path, "structured", client=ScriptedClient(bad))
    result = team.run_task(task)
    assert result["status"] == "incomplete" and result["reason"] == "invalid_structured_handoff"
    trace.close()


def test_new_request_cannot_reuse_team(tmp_path):
    task, team, trace = build(tmp_path, "summary")
    with pytest.raises(ValueError, match="New public request"):
        team.run_task("A different request")
    trace.close()


def test_pool_and_solo_route(tmp_path):
    assert len(POOL) == 9 and "constraint_analyst" in POOL
    with pytest.raises(ValueError):
        TeamSpec("x", (Member("invented_expert", "work"),))
    spec = select_team("Small task", {"solver": "Solve directly"})
    with Trace(tmp_path / "solo.jsonl", "solo") as trace:
        team = AgentTeam(spec, "summary", ScriptedClient(lambda *a: {"content": "done"}), trace, [], {"solver": []})
        assert team.run_task("Small task")["status"] == "completed"
        assert team.calls == 1 and team.sent == 0


def test_stable_role_prefix_and_reasoning_passback(tmp_path):
    task, team, trace = build(tmp_path, "adaptive")
    team.run_task(task)
    inputs = [r[0] for r in team.client.requests if r[0][0]["content"] == POOL["researcher"].system]
    assert all(m["reasoning_content"] == "thinking" for history in inputs for m in history if m["role"] == "assistant")
    original = team.agents["researcher"].messages
    assert not any("handoff_instruction" in str(m) for m in original)
    trace.close()
