"""Final notices must be checked before shared-call admission, without paid calls."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
import json
import threading

import pytest

from harness.agent import Agent, Observation, SessionBudget, SessionLimit, Tool
from harness.llm import ProviderError
from harness.subagents import SubagentTemplate, comparison_session
from harness.trace import Trace, read_trace
from tests.fakes import ScriptedClient


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import httpx
    monkeypatch.setattr(httpx.Client, "send", lambda *a, **k: pytest.fail("No network or paid calls"))


def first_input_estimate(messages, schemas):
    return (len(json.dumps(messages, ensure_ascii=False).encode("utf-8")) + 128 * len(messages)
            + len(json.dumps(schemas, ensure_ascii=False).encode("utf-8")))


@pytest.mark.parametrize("owner,submission", [("leader", False), ("subagent-1", False), ("leader", True)])
@pytest.mark.parametrize("fits", [False, True])
def test_shared_final_notice_checked_before_charging(tmp_path, owner, submission, fits):
    def policy(messages, tools, choice):
        assert "reserved final session call" in messages[-1]["content"]
        if submission:
            assert tools == ["submit"] and choice is None
            return {"calls": [("submit", {"answer": "ok"})]}
        assert choice == "none"
        return {"content": "report", "reasoning": "retained reasoning"}
    client = ScriptedClient(policy)
    client.cfg = replace(client.cfg, max_tokens=1, context_margin=0)
    budget = SessionBudget(model_calls=1 if owner == "leader" else 2)
    if owner != "leader":
        assert budget.reserve_report(owner)
    tools = [Tool("submit", "Submit", {"type": "object"},
                  lambda args, agent: Observation(json.dumps(args)))] if submission else []
    prompt = "Report existing evidence, uncertainty and unfinished work."
    with Trace(tmp_path / "trace.jsonl", "capacity") as trace:
        agent = Agent(owner, client, trace, "Worker", session_budget=budget, tools=tools,
                      submission_tool="submit" if submission else None)
        agent.append({"role": "user", "content": "task"})
        original = deepcopy(agent.messages)
        final_notice = agent.notice("This is the reserved final session call. Finish now.", prompt)
        expected = first_input_estimate(original + [final_notice], agent.schemas)
        old_estimate = agent.input_capacity()["estimated_input_tokens"]
        client.cfg = replace(client.cfg, context_window=(expected if fits else old_estimate) + 1)
        if fits:
            result = agent.run(None, prompt)
            assert result.status == "done" and result.turns == 1
            assert len(client.requests) == budget.snapshot()["model_calls"] == agent.model_calls == 1
            assert client.requests[0][0] == original + [final_notice]
            assert owner not in budget.report_reservations
        else:
            with pytest.raises(ProviderError, match="context_length"):
                agent.run(None, prompt)
            assert agent.messages == original + [final_notice]
            assert budget.snapshot()["model_calls"] == agent.model_calls == 0
            assert owner in budget.report_reservations
            assert not client.requests
    events = read_trace(trace.path)
    capacity = next(e for e in events if e["type"] == "input_capacity")
    assert capacity["context_len"] == len(original) + 1
    assert capacity["final_reason"] == "session_model_limit"
    assert capacity["estimated_input_tokens"] == expected
    assert capacity["remaining_tokens"] == (0 if fits else old_estimate - expected)
    assert sum(e["type"] == "llm_attempt" for e in events) == int(fits)
    assert not any(e["type"] == "llm_error" for e in events)


@pytest.mark.parametrize("mode", ["single", "mas"])
def test_capacity_rejection_has_equal_session_accounting_and_cleanup(tmp_path, mode):
    client = ScriptedClient(lambda *a: pytest.fail("Must reject before model dispatch"))
    client.cfg = replace(client.cfg, max_tokens=1, context_margin=0)
    with Trace(tmp_path / "trace.jsonl", mode) as trace:
        session = comparison_session(client, trace, [SubagentTemplate("worker", "Work", "Worker")], [],
                                     mode=mode, domain_tools=(), session_model_calls=1, max_turns=40)
        before = session.leader.messages + [{"role": "user", "content": "task"}]
        client.cfg = replace(client.cfg, context_window=first_input_estimate(before, session.leader.schemas) + 1)
        with pytest.raises(ProviderError) as failure:
            session.run("task")
        outcome = failure.value.session_outcome
        assert outcome.leader_status == "context_length" and not outcome.infra_affected
        assert outcome.budget["model_calls"] == outcome.budget["tool_calls"] == 0
        assert outcome.budget["leader_reserved_calls"] == outcome.budget["child_reserved_calls"] == 0
        assert outcome.budget["model_calls_unreserved"] == 1
        assert len(outcome.errors) == 1 and not session.children
        assert not client.requests


def test_receipt_anchored_check_includes_final_notice_and_verbatim_history(tmp_path):
    client = ScriptedClient(lambda *a: {"content": "first reply", "reasoning": "original reasoning"})
    client.cfg = replace(client.cfg, max_tokens=1, context_margin=0)
    budget = SessionBudget(model_calls=2)
    with Trace(tmp_path / "trace.jsonl", "receipt") as trace:
        agent = Agent("leader", client, trace, "Worker", session_budget=budget)
        agent.append({"role": "user", "content": "task"})
        agent.call()
        original = deepcopy(agent.messages)
        old_estimate = agent.input_capacity()["estimated_input_tokens"]
        client.cfg = replace(client.cfg, context_window=old_estimate + 1)
        with pytest.raises(ProviderError, match="context_length"):
            agent.run(None, "Report existing evidence.")
        assert agent.messages[:len(original)] == original
        assert len(agent.messages) == len(original) + 1
        assert agent.messages[-2]["reasoning_content"] == "original reasoning"
        assert len(client.requests) == budget.snapshot()["model_calls"] == agent.model_calls == 1
        assert budget.snapshot()["leader_reserved_calls"] == 1
        assert agent.input_capacity()["remaining_tokens"] < 0
    checks = [e for e in read_trace(trace.path) if e["type"] == "input_capacity"]
    assert len(checks) == 2 and checks[-1]["context_len"] == len(agent.messages)


def test_local_last_turn_notice_is_not_duplicated(tmp_path):
    client = ScriptedClient(lambda *a: {"content": "report"})
    client.cfg = replace(client.cfg, max_tokens=1, context_margin=0)
    budget = SessionBudget(model_calls=1)
    with Trace(tmp_path / "trace.jsonl", "local-final") as trace:
        agent = Agent("leader", client, trace, "Worker", session_budget=budget, max_turns=1)
        agent.append({"role": "user", "content": "task"})
        notice = agent.notice("This is the last model call allowed for this invocation.", "Report.")
        expected = first_input_estimate(agent.messages + [notice], agent.schemas)
        client.cfg = replace(client.cfg, context_window=expected + 1)
        assert agent.run(None, "Report.").status == "done"
        assert client.requests[0][0][-1] == notice
        assert len(client.requests[0][0]) == 3
        assert budget.snapshot()["model_calls"] == 1


def test_failed_preflight_does_not_steal_sibling_report_or_leader_call(tmp_path):
    budget = SessionBudget(model_calls=3)
    barrier = threading.Barrier(2)
    with Trace(tmp_path / "trace.jsonl", "siblings") as trace:
        agents = []
        for name in ("short", "long"):
            client = ScriptedClient(lambda *a: {"content": "report"})
            client.cfg = replace(client.cfg, max_tokens=1, context_margin=0, context_window=1000)
            assert budget.reserve_report(name)
            agent = Agent(name, client, trace, "Worker", session_budget=budget)
            agent.append({"role": "user", "content": "task"})
            agents.append(agent)
        def run(agent):
            barrier.wait(timeout=5)
            try:
                return agent.run(None, "Report." if agent.name == "short" else "details " * 1000).status
            except ProviderError as error:
                return error.kind
            finally:
                budget.release_report(agent.name)
        with ThreadPoolExecutor(2) as pool:
            assert list(pool.map(run, agents)) == ["done", "context_length"]
        snapshot = budget.snapshot()
        assert snapshot["model_calls"] == 1
        assert snapshot["leader_reserved_calls"] == 1 and snapshot["child_reserved_calls"] == 0
        assert [len(agent.client.requests) for agent in agents] == [1, 0]
        assert budget.take_model("leader", final=True) is False
        assert budget.snapshot()["model_calls"] == 2


def test_deadline_crossed_during_preflight_is_not_charged(monkeypatch):
    now = [0.0]
    monkeypatch.setattr("harness.agent.time.monotonic", lambda: now[0])
    budget = SessionBudget(model_calls=1, seconds=1)
    budget.start()
    def preflight(forced):
        assert forced
        now[0] = 2.0
    with pytest.raises(SessionLimit, match="session_time_limit"):
        budget.take_model("leader", preflight=preflight)
    assert budget.snapshot()["model_calls"] == 0
    assert budget.snapshot()["leader_reserved_calls"] == 1


def test_provider_failure_after_successful_preflight_is_still_charged(tmp_path):
    def fail(*args):
        raise ProviderError("http_500", "scripted failure", 500)
    client = ScriptedClient(fail)
    budget = SessionBudget(model_calls=1)
    with Trace(tmp_path / "trace.jsonl", "provider-error") as trace:
        agent = Agent("leader", client, trace, "Worker", session_budget=budget)
        with pytest.raises(ProviderError, match="http_500"):
            agent.run("task", "Report.")
        assert budget.snapshot()["model_calls"] == agent.model_calls == len(client.requests) == 1
        assert budget.snapshot()["leader_reserved_calls"] == 0
    events = read_trace(trace.path)
    assert sum(e["type"] == "llm_attempt" for e in events) == 1
    assert sum(e["type"] == "llm_error" for e in events) == 1
