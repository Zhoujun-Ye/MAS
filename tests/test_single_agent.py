import json

import pytest

from fakes import ScriptedClient
from harness.agent import Observation, Tool
from harness.llm import ProviderError
from harness.single_agent import SingleAgent
from harness.catalog import CapabilityTemplate
from harness.session import comparison_session, resolve_mode
from harness.trace import Trace, contexts, read_trace, validate


def tools():
    return [Tool(name, name, {"type": "object", "additionalProperties": False},
                 lambda args, agent, name=name: Observation(name + " raw observation"), budgeted=True, read_only=name == "read")
            for name in ("read", "write")]


def test_single_retains_full_task_tools_observations_and_reasoning(tmp_path):
    def policy(messages, names, choice):
        assert set(names) == {"read", "write"}
        assert messages[1]["content"] == "FULL ORIGINAL TASK"
        replies = [m for m in messages if m["role"] == "assistant"]
        for index, reply in enumerate(replies):
            assert reply["reasoning_content"] == f"verbatim reasoning {index}"
        count = len(replies)
        if count < 3:
            return {"calls": [(("read", "delegate", "write")[count], {})],
                    "reasoning": f"verbatim reasoning {count}"}
        assert "read raw observation" in json.dumps(messages)
        assert "write raw observation" in json.dumps(messages)
        return {"content": "final report", "reasoning": "verbatim reasoning 3"}
    client = ScriptedClient(policy)
    with Trace(tmp_path / "trace.jsonl", "single") as trace:
        trace.emit("run_start")
        single = SingleAgent(client, trace, tools(), workspace_audit=lambda: {"files": {}})
        outcome = single.run("FULL ORIGINAL TASK")
        assert outcome.status == "done" and len(outcome.errors) == 1
        assert not single.templates and not single.members
        assert single.context_mode == "full_task_and_own_history"
        for previous, current in zip(client.requests, client.requests[1:]):
            assert current[0][:len(previous[0])] == previous[0]
        trace.emit("final", text=outcome.text)
        trace.emit("run_end", status="completed")
        with pytest.raises(ValueError, match="once"):
            single.run("again")
    events = read_trace(trace.path)
    assert validate(events) == []
    assert set(contexts(events)) == {"leader"}
    assert all(e["usage_role"] == "single" for e in events if e["type"] == "llm_call")
    assert [e["phase"] for e in events if e["type"] == "session_workspace_snapshot"] == ["before", "after"]
    assert not any(e["type"] == "delegation_start" for e in events)


def test_single_spends_same_session_ceiling_and_reserves_final_call(tmp_path):
    client = ScriptedClient(lambda messages, names, choice:
        {"content": "final"} if choice == "none" else {"calls": [("read", {})]})
    with Trace(tmp_path / "trace.jsonl", "limits") as trace:
        single = SingleAgent(client, trace, tools(), session_model_calls=3, session_tool_calls=2)
        outcome = single.run("task")
    assert outcome.status == "done" and len(client.requests) == 3
    assert client.requests[-1][2] == "none"
    assert single.leader.max_turns == 3 and single.leader.budget.limit == 2
    assert outcome.budget["model_calls"] == 3 and outcome.budget["tool_calls"] == 2


@pytest.mark.parametrize('kind,infra', [('execution_interrupted', False), ('execution_transport', True)])
def test_execution_history_does_not_infer_infra_from_unconfirmed_interruption(tmp_path, kind, infra):
    tool = Tool('execute', 'execute', {'type': 'object'},
                lambda *a: Observation('execution not confirmed', {'error': True, 'error_kind': kind}), budgeted=True)
    client = ScriptedClient(lambda messages, names, choice:
                            {'content': 'partial work retained'} if any(m.get('tool_calls') for m in messages)
                            else {'calls': [('execute', {})]})
    with Trace(tmp_path / 'trace.jsonl', kind) as trace:
        session = SingleAgent(client, trace, [tool])
        outcome = session.run('task')
    assert outcome.infra_affected is infra
    assert len(outcome.errors) == 1 and outcome.errors[0]['error_kind'] == kind
    assert len(client.requests) == 2


@pytest.mark.parametrize("mode", ["single", "team"])
def test_pair_factory_preserves_single_grants_and_team_coordination_only(tmp_path, mode):
    with Trace(tmp_path / "trace.jsonl", mode) as trace:
        session = comparison_session(ScriptedClient(lambda *args: {"content": "done"}), trace,
            [CapabilityTemplate("reader", "read", "read", ("read",))], tools(),
            mode=mode, domain_tools=(name for name in ("read", "write")),
            session_model_calls=65, session_tool_calls=110)
        assert session.leader.max_turns == 65 and session.leader.budget.limit == 110
        assert ("write" in session.leader.tools) == (mode == "single")
        assert ("read" in session.leader.tools) == (mode == "single")
        assert isinstance(session, SingleAgent) == (mode == "single")
        for limits in ({"max_turns": 2}, {"tool_budget": 1}):
            with pytest.raises(ValueError, match="full shared"):
                comparison_session(session.client, trace, [CapabilityTemplate("reader", "read", "read", ("read",))], tools(), mode=mode,
                                   domain_tools=("read", "write"), **limits)


@pytest.mark.parametrize("kwargs", [{"mode": "unknown"}, {"mode": "single", "delegated": True},
                                    {"mode": "team", "delegated": False}, {"delegated": "false"}])
def test_mode_conflicts_fail_closed(kwargs):
    with pytest.raises(ValueError):
        resolve_mode(**kwargs)


def test_single_preserves_provider_failure_and_audit_evidence(tmp_path):
    def fail(*args):
        raise ProviderError("http", "balance", 402)
    with Trace(tmp_path / "trace.jsonl", "failure") as trace:
        single = SingleAgent(ScriptedClient(fail), trace, tools(), workspace_audit=lambda: {"files": {}})
        with pytest.raises(ProviderError) as error:
            single.run("task")
        assert error.value.session_outcome.infra_affected
        assert len(error.value.session_outcome.errors) == 1
        assert len(single.client.requests) == 1
    events = read_trace(trace.path)
    assert len([e for e in events if e["type"] == "session_workspace_snapshot"]) == 2
    assert events[-1]["type"] == "session_end"


def test_single_cannot_expand_explicit_capability_ceiling(tmp_path):
    with Trace(tmp_path / "trace.jsonl", "grants") as trace:
        client = ScriptedClient(lambda *args: {"content": "done"})
        single = SingleAgent(client, trace, tools(), domain_tools=("read",))
        assert set(single.leader.tools) == {"read"}
        with pytest.raises(ValueError):
            SingleAgent(client, trace, tools(), domain_tools=("unregistered",))
        with pytest.raises(TypeError):
            SingleAgent(client, trace, tools(), templates=[CapabilityTemplate("bad", "bad", "bad")])
