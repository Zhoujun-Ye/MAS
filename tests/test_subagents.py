import json

import pytest

from fakes import ScriptedClient
from harness.agent import Observation, Tool
from harness.llm import ProviderError
from harness.subagents import LeaderSubagent, SubagentTemplate
from harness.trace import Trace, read_trace, validate


def build(tmp_path, policy, **kwargs):
    trace = Trace(tmp_path / "trace.jsonl", "test")
    trace.emit("run_start")
    client = ScriptedClient(policy)
    template = SubagentTemplate("research", "Read evidence", "Child system", ("read",), max_turns=2, tool_budget=1)
    tool = Tool("read", "Read shared evidence", {"type": "object"},
                lambda args, agent: Observation("shared evidence"), budgeted=True)
    session = LeaderSubagent(client, trace, [template], [tool], **kwargs)
    return session, client, trace


def test_delegation_resume_and_context(tmp_path):
    def policy(messages, tools, choice):
        if "delegate" in tools:
            reports = [m for m in messages if m["role"] == "tool"]
            if len(reports) < 2:
                args = {"template": "research", "task": "Read evidence", "context": "selected context"}
                if reports:
                    args["resume_id"] = json.loads(reports[-1]["content"])["agent_id"]
                return {"calls": [("delegate", args)]}
            return {"content": "Integrated answer"}
        assert "leader secret" not in json.dumps(messages)
        assert "shared instructions" in messages[0]["content"]
        assert tools == ["read"]
        if messages[-1]["role"] == "user" and choice != "none":
            return {"calls": [("read", {})]}
        return {"content": "Evidence report"}

    session, client, trace = build(tmp_path, policy, project_context="shared instructions")
    result = session.run("leader secret")
    assert result.text == "Integrated answer"
    assert result.status == "done"
    assert result.leader_status == "done"
    assert result.delegations[-1]["outcome"] == "done"
    assert any(e["error_kind"] == "budget_exhausted" for e in result.tool_events)
    assert len(session.children) == 1
    child = session.children["subagent-1"]
    assert child.budget.used == 1  # resume never refreshes tool allowance
    assert sum(m["role"] == "user" and m["content"].startswith('{"task"') for m in child.messages) == 2
    assert any("budget is exhausted" in m.get("content", "") for m in child.messages)
    trace.emit("final", text=result.text)
    trace.emit("run_end", status="completed")
    trace.close()
    assert validate(read_trace(trace.path)) == []


@pytest.mark.parametrize("error", [ProviderError("http", "bad request", 400),
                                  ProviderError("context_length", "too large")])
def test_child_failure_is_not_success(tmp_path, error):
    def policy(messages, tools, choice):
        if "delegate" not in tools:
            raise error
        if messages[-1]["role"] == "user":
            return {"calls": [("delegate", {"template": "research", "task": "work"})]}
        return {"content": messages[-1]["content"]}
    session, _, trace = build(tmp_path, policy)
    result = session.run("task")
    assert result.status == "done"
    assert result.errors[0]["error_kind"] == error.kind
    report = json.loads(result.text)
    assert report["status"] in {"provider_error", "context_length"}
    assert session._delegate({"template": "research", "task": "retry", "resume_id": "subagent-1"}, None).meta["error"]
    trace.close()


def test_fatal_stops_before_another_call_or_tool(tmp_path):
    def policy(messages, tools, choice):
        if "delegate" not in tools:
            raise ProviderError("http", "balance", 402)
        return {"calls": [("delegate", {"template": "research", "task": "work"}), ("read", {})]}
    session, client, trace = build(tmp_path, policy, leader_tools=("read",))
    with pytest.raises(ProviderError) as failure:
        session.run("task")
    assert failure.value.session_outcome.status == "incomplete"
    assert failure.value.session_outcome.child_statuses == {"subagent-1": "provider_error"}
    assert len(client.requests) == 2
    assert session.leader.budget.used == 0
    trace.close()


def test_permissions_and_limits(tmp_path):
    session, client, trace = build(tmp_path, lambda *args: {"content": "done"}, max_subagents=1, max_delegations=2)
    args = {"template": "research", "task": "work"}
    session._delegate(args, None)
    assert session._delegate(args, None).meta["error"]
    assert session._delegate(dict(args, resume_id="unknown"), None).meta["error"]
    session._delegate(dict(args, resume_id="subagent-1"), None)
    assert session._delegate(dict(args, resume_id="subagent-1"), None).meta["error"]
    child = session.children["subagent-1"]
    denied = child.run_tool({"id": "denied", "function": {"name": "delegate", "arguments": "{}"}})
    assert denied.meta["error"]
    with pytest.raises(ValueError, match="Tool grants"):
        LeaderSubagent(client, trace, list(session.templates.values()), list(session.tools.values()), allowed_tools=[])
    trace.close()


def test_partial_report_and_single_use(tmp_path):
    session, _, trace = build(tmp_path, lambda *args: {"calls": [("read", {})]})
    obs = session._delegate({"template": "research", "task": "work"}, None)
    assert json.loads(obs.text)["status"] == "partial"
    session.started = True
    with pytest.raises(ValueError, match="once"):
        session.run("task")
    trace.close()


def test_leader_only_and_frozen_template_tools(tmp_path):
    names = ["read"]
    template = SubagentTemplate("reader", "Read", "Read", names)
    names.append("write")
    assert template.tools == ("read",)
    with Trace(tmp_path / "leader.jsonl", "leader-only") as trace:
        client = ScriptedClient(lambda messages, tools, choice: {"content": "direct answer"})
        session = LeaderSubagent(client, trace, [])
        assert session.run("task").text == "direct answer"
        assert client.requests[0][1] == []


@pytest.mark.parametrize("resume_id", ["", " ", "subagent-0", "subagent-999", None])
def test_invalid_resume_never_creates_child(tmp_path, resume_id):
    session, client, trace = build(tmp_path, lambda *args: {"content": "done"})
    obs = session.leader.run_tool({"id": "bad", "function": {
        "name": "delegate", "arguments": json.dumps({
            "template": "research", "task": "continue", "resume_id": resume_id})}})
    assert obs.meta["error"]
    assert not session.children
    assert session.delegations == 0
    assert not client.requests
    trace.close()


@pytest.mark.parametrize("finish", ["length", "tool_calls"])
def test_call_limit_has_no_hidden_recovery(tmp_path, finish):
    def policy(messages, tools, choice):
        return {"content": "partial", "finish": finish, "calls": [("read", {})]}
    session, client, trace = build(tmp_path, policy)
    template = session.templates["research"]
    from dataclasses import replace
    session.templates["research"] = replace(template, max_turns=1)
    report = json.loads(session._delegate({"template": "research", "task": "work"}, None).text)
    assert report["status"] == "partial"
    assert report["outcome"] == ("length" if finish == "length" else "turn_limit")
    assert len(client.requests) == 1
    assert client.efforts == [None]
    child = session.children["subagent-1"]
    assert child.budget.used == 0
    trace.close()


def test_partial_resume_preserves_history_of_attempts(tmp_path):
    def policy(messages, tools, choice):
        if "delegate" in tools:
            reports = [m for m in messages if m["role"] == "tool"]
            if len(reports) == 2:
                return {"content": "integrated"}
            args = {"template": "research", "task": "work"}
            if reports:
                args["resume_id"] = "subagent-1"
            return {"calls": [("delegate", args)]}
        previous = [m for m in messages if m["role"] == "assistant"]
        return {"content": "report", "finish": "stop" if previous else "length"}
    session, client, trace = build(tmp_path, policy)
    result = session.run("task")
    assert result.status == "done"
    assert result.child_statuses == {"subagent-1": "completed"}
    assert [report["status"] for report in result.delegations] == ["partial", "completed"]
    assert all(effort is None for effort in client.efforts)
    trace.close()
