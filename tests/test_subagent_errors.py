from dataclasses import replace

import pytest

from fakes import ScriptedClient
from harness.agent import Observation, Tool
from harness.llm import ProviderError
from harness.subagents import LeaderSubagent, SubagentTemplate
from harness.trace import Trace, read_trace


@pytest.mark.parametrize("limit,resume,expected", [
    ("delegations", False, "delegation_limit"),
    ("delegations", True, "delegation_limit"),
    ("children", False, "subagent_limit"),
    ("invalid", True, "invalid_arguments"),
])
def test_rejected_assignment_remains_in_result(tmp_path, limit, resume, expected):
    def policy(messages, tools, choice):
        if "delegate" not in tools:
            return {"content": "child done"}
        count = sum(m["role"] == "tool" for m in messages)
        if count == 2:
            return {"content": "leader finished"}
        args = {"template": "worker", "task": "first" if count == 0 else "second"}
        if count and resume:
            args["resume_id"] = "" if limit == "invalid" else "subagent-1"
        return {"calls": [("delegate", args)]}
    with Trace(tmp_path / "trace.jsonl", "test") as trace:
        session = LeaderSubagent(ScriptedClient(policy), trace,
                                [SubagentTemplate("worker", "Work", "Worker")],
                                max_delegations=1 if limit == "delegations" else 3,
                                max_subagents=1)
        result = session.run("task")
        assert result.status == "done"
        rejected = [r for r in result.delegations if r["status"] == "rejected"]
        assert len(rejected) == 1
        assert rejected[0]["args"]["task"] == "second"
        assert rejected[0]["error_kind"] == expected
        assert result.errors[0]["error_kind"] == expected
        assert len(session.children) == session.delegations == 1
    end = [e for e in read_trace(trace.path) if e["type"] == "session_end"][0]
    assert end["status"] == "done"
    assert end["errors"] == result.errors


@pytest.mark.parametrize("owner", ["leader", "child"])
@pytest.mark.parametrize("kind", ["exception", "transport", "nonzero", "permission", "arguments"])
def test_tool_outcomes_are_classified(tmp_path, owner, kind):
    def operation(args, agent):
        if kind == "exception":
            raise OSError("workspace unavailable")
        if kind == "transport":
            return Observation("transport failed", {"error": True, "error_kind": "execution_transport"})
        return Observation("test failed", {"error": False, "exit_code": 1})
    tool = Tool("read", "Read", {"type": "object", "additionalProperties": False}, operation, budgeted=True)
    if kind == "permission":
        tool.preflight = lambda args, agent: Observation("denied", {"error": True})
    def policy(messages, tools, choice):
        if "delegate" in tools:
            if messages[-1]["role"] == "user":
                return {"calls": [("delegate", {"template": "worker", "task": "read"})]}
            return {"content": "finished"}
        if messages[-1]["role"] == "user":
            return {"calls": [("read", {"invalid": True} if kind == "arguments" else {})]}
        return {"content": "report"}
    with Trace(tmp_path / "trace.jsonl", "test") as trace:
        session = LeaderSubagent(ScriptedClient(policy), trace,
                                [SubagentTemplate("worker", "Work", "Worker", ("read",))] if owner == "child" else [],
                                [tool], leader_tools=("read",) if owner == "leader" else ())
        result = session.run("task")
        assert result.status == "done"
        assert len(result.tool_events) == 1
        expected = dict(exception="execution_error", transport="execution_transport",
                        nonzero="command_exit", permission="permission_denied", arguments="invalid_arguments")[kind]
        assert result.tool_events[0]["error_kind"] == expected
        assert bool(result.errors) == (kind != "nonzero")
        if owner == "child" and kind != "nonzero":
            assert result.child_statuses == {"subagent-1": "completed"}
        agent = session.leader if owner == "leader" else session.children["subagent-1"]
        assert agent.budget.used == (0 if kind in {"permission", "arguments"} else 1)


def test_leader_context_limit_is_not_provider_failure(tmp_path):
    client = ScriptedClient(lambda *args: pytest.fail("must not call the model"))
    client.cfg = replace(client.cfg, context_window=1)
    with Trace(tmp_path / "trace.jsonl", "test") as trace:
        session = LeaderSubagent(client, trace, [])
        with pytest.raises(ProviderError) as failure:
            session.run("task")
        result = failure.value.session_outcome
        assert result.status == "incomplete"
        assert result.errors[0]["status"] == "context_length"
        assert result.errors[0]["error_kind"] == "context_length"
        assert not client.requests


@pytest.mark.parametrize("kind", ["failure", "forbidden_delegate"])
def test_resume_keeps_prior_tool_failure_evidence(tmp_path, kind):
    def operation(args, agent):
        raise OSError("workspace unavailable")
    tool = Tool("read", "Read", {"type": "object"}, operation, budgeted=True)
    def policy(messages, tools, choice):
        if messages[0]["content"].startswith("You are the leader"):
            count = sum(m["role"] == "tool" for m in messages)
            if count == 2:
                return {"content": "finished"}
            args = {"template": "worker", "task": "work"}
            if count:
                args["resume_id"] = "subagent-1"
            return {"calls": [("delegate", args)]}
        if len(messages) == 2:
            return {"calls": [("read" if kind == "failure" else "delegate", {})]}
        return {"content": "report"}
    with Trace(tmp_path / "trace.jsonl", "test") as trace:
        session = LeaderSubagent(ScriptedClient(policy), trace,
                                [SubagentTemplate("worker", "Work", "Worker", ("read",))], [tool])
        result = session.run("task")
        assert session.delegations == 2
        assert len(session.children) == 1
        assert result.status == "done"
        assert len(result.errors) == 1
        assert result.errors[0]["agent_id"] == "subagent-1"
        assert result.errors[0]["error_kind"] == ("execution_error" if kind == "failure" else "permission_denied")
