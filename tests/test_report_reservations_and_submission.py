"""No-network regressions for report admission, terminal tools and mixed batches."""

import json
import threading

import pytest

from benchmarks.kramabench.adapter import make_session, parse_submission
from benchmarks.kramabench.offline import FixtureWorkspace
from harness.agent import Agent, Budget, Observation, SessionBudget, Tool
from harness.llm import ProviderError
from harness.subagents import LeaderSubagent, SubagentTemplate
from harness.trace import Trace, read_trace, validate
from tests.fakes import ScriptedClient


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import httpx
    monkeypatch.setattr(httpx.Client, "send", lambda *a, **k: pytest.fail("Paid/network call forbidden"))


def test_parallel_children_and_leader_all_report_at_shared_boundary(tmp_path):
    barrier = threading.Barrier(2)
    def policy(messages, tools, choice):
        if choice == "none":
            seen = [m["content"] for m in messages if m["role"] == "tool"]
            return {"content": "FINAL " + " ".join(seen)}
        if "delegate" in tools:
            return {"calls": [("delegate", {"template": "worker", "task": str(i)}) for i in range(2)]}
        if not any(m["role"] == "assistant" for m in messages):
            barrier.wait(timeout=5)
        return {"calls": [("read", {})]}
    tool = Tool("read", "Read", {"type": "object"},
                lambda args, agent: Observation("EVIDENCE " + agent.name), budgeted=True)
    client = ScriptedClient(policy)
    with Trace(tmp_path / "trace.jsonl", "boundary") as trace:
        trace.emit("run_start")
        session = LeaderSubagent(client, trace, [SubagentTemplate("worker", "Read", "Worker", ("read",))],
                                [tool], session_model_calls=7)
        result = session.run("task")
        assert result.status == "done" and result.budget["model_calls"] == 7
        assert len(result.delegations) == 2
        for report in result.delegations:
            assert report["status"] == "completed"
            assert "EVIDENCE " + report["agent_id"] in report["report"]
            assert report["usage"]["model_calls"] >= 2
            assert report["usage"]["tool_calls"] == report["usage"]["budgeted_tool_calls"]
        assert sum(r["usage"]["model_calls"] for r in result.delegations) + 2 == 7
        assert result.budget["child_reserved_calls"] == result.budget["leader_reserved_calls"] == 0
        assert all(r["usage"]["session_model_calls_remaining"] >= 1 for r in result.delegations)
        trace.emit("final", text=result.text)
        trace.emit("run_end", status="completed")
    assert validate(read_trace(trace.path)) == []


@pytest.mark.parametrize("failure", [None, "provider", "unexpected"])
def test_unused_reservation_released_and_failure_not_double_counted(tmp_path, failure):
    def policy(messages, tools, choice):
        if "delegate" in tools:
            if messages[-1]["role"] == "user":
                return {"calls": [("delegate", {"template": "worker", "task": "local"})]}
            report = json.loads(messages[-1]["content"])
            assert report["usage"]["model_calls"] == 1
            assert report["agent_id"] == "subagent-1"
            return {"content": "integrated"}
        if failure == "provider":
            raise ProviderError("transport", "fixture")
        if failure == "unexpected":
            raise RuntimeError("fixture client exception")
        return {"content": "early report"}
    with Trace(tmp_path / "trace.jsonl", "release") as trace:
        session = LeaderSubagent(ScriptedClient(policy), trace, [SubagentTemplate("worker", "Read", "Worker")],
                                session_model_calls=8)
        result = session.run("task")
        assert result.budget["model_calls"] == 3
        assert result.budget["model_calls_unreserved"] == 5
        assert result.budget["child_reserved_calls"] == 0
        assert len(result.delegations) == 1
        assert len(result.errors) == bool(failure)
        if failure:
            assert result.errors[0]["agent_id"] == "subagent-1"
            assert result.infra_affected


def test_resume_usage_is_delta_and_reserves_again(tmp_path):
    def policy(messages, tools, choice):
        if "delegate" not in tools:
            return {"content": "report"}
        reports = [json.loads(m["content"]) for m in messages if m["role"] == "tool"]
        if len(reports) == 2:
            return {"content": "done"}
        args = {"template": "worker", "task": "local"}
        if reports:
            args["resume_id"] = reports[0]["agent_id"]
        return {"calls": [("delegate", args)]}
    with Trace(tmp_path / "trace.jsonl", "resume") as trace:
        session = LeaderSubagent(ScriptedClient(policy), trace, [SubagentTemplate("worker", "Read", "Worker")],
                                session_model_calls=5)
        result = session.run("task")
        assert result.status == "done" and len(session.children) == 1
        assert [r["usage"]["model_calls"] for r in result.delegations] == [1, 1]
        assert result.budget["model_calls"] == 5
        assert result.budget["model_calls_unreserved"] == 0


def test_reservation_admission_is_atomic():
    budget = SessionBudget(model_calls=3)
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(8) as pool:
        admitted = list(pool.map(budget.reserve_report, [str(i) for i in range(8)]))
    assert sum(admitted) == 2
    assert budget.snapshot()["model_calls_unreserved"] == 0
    for i, accepted in enumerate(admitted):
        if accepted:
            assert budget.take_model(str(i)) is True
    assert budget.take_model("leader") is True
    assert budget.snapshot()["model_calls"] == 3


def test_contiguous_concurrent_groups_preserve_serial_barriers(tmp_path):
    barrier = threading.Barrier(2)
    events = []
    def work(args, agent):
        group = args["group"]
        assert events.count("serial") == group
        barrier.wait(timeout=5)
        events.append("parallel")
        return Observation("ok")
    def serial(args, agent):
        assert events == ["parallel", "parallel"]
        events.append("serial")
        return Observation("barrier")
    tools = [Tool("parallel", "Concurrent", {"type": "object"}, work, concurrent=True),
             Tool("serial", "Barrier", {"type": "object"}, serial)]
    def policy(messages, names, choice):
        if messages[-1]["role"] == "user":
            return {"calls": [("parallel", {"group": 0}), ("parallel", {"group": 0}),
                              ("serial", {}), ("parallel", {"group": 1}), ("parallel", {"group": 1})]}
        return {"content": "done"}
    with Trace(tmp_path / "trace.jsonl", "groups") as trace:
        agent = Agent("a", ScriptedClient(policy), trace, "Worker", tools=tools)
        assert agent.run("task", "report").status == "done"
        assert events == ["parallel", "parallel", "serial", "parallel", "parallel"]
        assert len([m for m in agent.messages if m["role"] == "tool"]) == 5


def test_disobedient_reserved_final_has_actual_turn_and_limit_reason(tmp_path):
    client = ScriptedClient(lambda *args: {"calls": [("write", {})]})
    effects = []
    with Trace(tmp_path / "trace.jsonl", "final") as trace:
        session = LeaderSubagent(client, trace, [],
            [Tool("write", "Write", {"type": "object"}, lambda *a: effects.append(True))],
            leader_tools=("write",), session_model_calls=1, max_turns=40)
        result = session.run("task")
        assert result.leader_status == "session_model_limit" and result.turns == 1
        assert not effects
        assert {"reason": "session_model_limit", "agent": "leader"} in result.budget["limit_events"]


VALID = {"answer": 4, "pipeline_code": "print(4)", "evidence": "fixture", "unfinished": []}


@pytest.mark.parametrize("mode", ["single", "mas"])
def test_invalid_submit_is_visible_and_corrected_within_budget(tmp_path, mode):
    def policy(messages, tools, choice):
        observations = [m for m in messages if m["role"] == "tool"]
        if not observations:
            return {"calls": [("submit", {"answer": 4})]}
        assert "Invalid submit arguments" in observations[-1]["content"]
        assert tools == ["submit"] and choice is None
        return {"calls": [("submit", VALID)]}
    client = ScriptedClient(policy)
    with Trace(tmp_path / "trace.jsonl", mode) as trace:
        session, _ = make_session(client, trace, FixtureWorkspace(tmp_path / "fixture"),
                                  mode=mode, session_model_calls=2, session_tool_calls=0)
        result = session.run("question")
        assert result.status == "done" and parse_submission(result.text) == VALID
        assert result.budget["model_calls"] == 2 and result.budget["tool_calls"] == 0
        assert len(result.errors) == 1 and result.errors[0]["error_kind"] == "invalid_arguments"
        assert client.response_formats == [None, None]
        assert not session.children


@pytest.mark.parametrize("kind", ["invalid", "mixed", "text"])
def test_final_submission_failure_has_no_hidden_call_or_side_effect(tmp_path, kind):
    def policy(messages, tools, choice):
        assert tools == ["submit"] and choice is None
        if kind == "text":
            return {"content": json.dumps(VALID)}
        if kind == "mixed":
            return {"calls": [("submit", VALID), ("terminal", {"command": "fixture_average"})]}
        return {"calls": [("submit", {"answer": 4})]}
    client = ScriptedClient(policy)
    workspace = FixtureWorkspace(tmp_path / "fixture")
    with Trace(tmp_path / "trace.jsonl", kind) as trace:
        session, _ = make_session(client, trace, workspace, mode="single", session_model_calls=1)
        result = session.run("question")
        assert result.status == "incomplete" and session.leader.submission is None
        assert len(client.requests) == 1
        assert result.turns == 1
        assert not list(workspace.work.iterdir())


@pytest.mark.parametrize("arguments", [
    '{"answer": 4, "answer": 5, "pipeline_code": "", "evidence": "", "unfinished": []}',
    '{"answer": NaN, "pipeline_code": "", "evidence": "", "unfinished": []}',
    '{"answer": 4, "pipeline_code": 5, "evidence": "", "unfinished": []}',
])
def test_submit_rejects_ambiguous_or_invalid_arguments_without_accepting(tmp_path, arguments):
    with Trace(tmp_path / "trace.jsonl", "invalid-arguments") as trace:
        session, _ = make_session(ScriptedClient(lambda *a: {}), trace, FixtureWorkspace(tmp_path / "fixture"),
                                  mode="single")
        obs = session.leader.run_tool({"id": "bad", "function": {"name": "submit", "arguments": arguments}})
        assert obs.meta["error_kind"] == "invalid_arguments"
        assert session.leader.submission is None
        assert session.session_budget.snapshot()["tool_calls"] == 0
