"""No-network regressions for report admission, terminal tools and mixed batches."""

import json
import threading

import pytest

from benchmarks.kramabench.adapter import make_session, parse_submission
from benchmarks.kramabench.offline import FixtureWorkspace, PIPELINE
from harness.agent import Agent, Observation, SessionBudget, Tool
from harness.single_agent import SingleAgent
from harness.trace import Trace
from tests.fakes import ScriptedClient


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import httpx
    monkeypatch.setattr(httpx.Client, "send", lambda *a, **k: pytest.fail("Paid/network call forbidden"))





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
        session = SingleAgent(client, trace,
            [Tool("write", "Write", {"type": "object"}, lambda *a: effects.append(True))],
            domain_tools=("write",), session_model_calls=1, max_turns=40)
        result = session.run("task")
        assert result.leader_status == "session_model_limit" and result.turns == 1
        assert not effects
        assert {"reason": "session_model_limit", "agent": "leader"} in result.budget["limit_events"]


VALID = {"answer": 4, "pipeline_path": "pipeline.py", "evidence": "fixture", "unfinished": []}


@pytest.mark.parametrize("mode", ["single"])
def test_invalid_submit_is_visible_and_corrected_within_budget(tmp_path, mode):
    def policy(messages, tools, choice):
        observations = [m for m in messages if m["role"] == "tool"]
        if not observations:
            return {"calls": [("submit", {"answer": 4})]}
        assert "Invalid submit arguments" in observations[-1]["content"]
        assert tools == ["submit"] and choice is None
        return {"calls": [("submit", VALID)]}
    client = ScriptedClient(policy)
    workspace = FixtureWorkspace(tmp_path / "fixture")
    workspace.calculate({"command": "fixture_average"}, None)
    with Trace(tmp_path / "trace.jsonl", mode) as trace:
        session, _ = make_session(client, trace, workspace,
                                  mode=mode, session_model_calls=2, session_tool_calls=0)
        result = session.run("question")
        assert result.status == "done" and parse_submission(result.text) == dict(answer=4, pipeline_code=PIPELINE, evidence="fixture", unfinished=[])
        assert result.budget["model_calls"] == 2 and result.budget["tool_calls"] == 0
        assert len(result.errors) == 1 and result.errors[0]["error_kind"] == "invalid_arguments"
        assert client.response_formats == [None, None]
        assert not session.members


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
    '{"answer": 4, "answer": 5, "pipeline_path": "", "evidence": "", "unfinished": []}',
    '{"answer": NaN, "pipeline_path": "", "evidence": "", "unfinished": []}',
    '{"answer": 4, "pipeline_path": 5, "evidence": "", "unfinished": []}',
])
def test_submit_rejects_ambiguous_or_invalid_arguments_without_accepting(tmp_path, arguments):
    with Trace(tmp_path / "trace.jsonl", "invalid-arguments") as trace:
        session, _ = make_session(ScriptedClient(lambda *a: {}), trace, FixtureWorkspace(tmp_path / "fixture"),
                                  mode="single")
        obs = session.leader.run_tool({"id": "bad", "function": {"name": "submit", "arguments": arguments}})
        assert obs.meta["error_kind"] == "invalid_arguments"
        assert session.leader.submission is None
        assert session.session_budget.snapshot()["tool_calls"] == 0
