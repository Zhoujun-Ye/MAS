"""Scripted Team protocol tests; no provider or paid evaluator access."""

import json
import threading

import pytest

from fakes import ScriptedClient
from harness.agent import Observation, Tool
from harness.catalog import CapabilityTemplate
from harness.llm import ProviderError
from harness.team import AgentTeam
from harness.trace import Trace, contexts, llm_inputs, read_trace, validate


def call(name, **args):
    return {"calls": [(name, args)]}


def names_used(messages):
    return [c["function"]["name"] for m in messages for c in m.get("tool_calls", [])]


def inbox(messages):
    return [r for m in messages if m["role"] == "user" and m["content"].startswith("Team inbox")
            for r in json.loads(m["content"].split("\n", 1)[1])]


def finish_when_returned(team, messages, tools, tasks=2):
    if "finish_team" in names_used(messages) or not tools:
        return {"content": "final evidence"}
    with team.condition:
        returned = len(team.reports) >= tasks and not any(m.active for m in team.members.values())
    return call("finish_team", reason="all returned") if returned else call("wait_event", timeout_seconds=0.02)


def make(trace, policy, tools=(), **kw):
    return AgentTeam(ScriptedClient(policy), trace,
        [CapabilityTemplate("worker", "execute", "WORKER", tuple(t.name for t in tools))],
        tools, session_model_calls=kw.pop("session_model_calls", 40), session_seconds=5, **kw)


def test_peer_delivery_async_turn_safety_and_final_barrier(tmp_path):
    release = threading.Event()
    effects = []
    def work(args, agent):
        assert release.wait(2), "Peer must run while the first worker's tool is in flight"
        effects.append("write finished")
        return Observation("artifact ready")
    def policy(messages, tools, choice):
        used = names_used(messages)
        if "spawn_worker" in tools or messages[0]["content"].startswith("Coordinate"):
            if not used:
                return {"calls": [("spawn_worker", dict(template="worker", task=n)) for n in ("produce", "ask")]}
            result = finish_when_returned(team, messages, tools)
            if result.get("content"):
                assert effects == ["write finished"]
                assert not any(m.active for m in team.members.values())
                assert "artifact ready" in json.dumps(inbox(messages))
            return result
        assert "PRIVATE_FULL_TASK" not in json.dumps(messages)
        task = json.loads(messages[1]["content"])["task"]
        if task == "produce":
            if not used:
                return call("work")
            question = next(r for r in inbox(messages) if r["needs_reply"])
            if "send_message" not in used:
                return call("send_message", to="worker-2", content="artifact ready", kind="answer", reply_to=question["message_id"])
            return {"content": "artifact ready"}
        if not used:
            return call("send_message", to="worker-1", content="Which artifact?", kind="question", needs_reply=True)
        release.set()
        if not any(r["kind"] == "answer" for r in inbox(messages)):
            return call("wait_event", timeout_seconds=0.02)
        return {"content": "peer answer checked"}
    with Trace(tmp_path / "trace.jsonl", "peer") as trace:
        trace.emit("run_start")
        team = make(trace, policy, [Tool("work", "work", {"type": "object"}, work, budgeted=True)])
        result = team.run("PRIVATE_FULL_TASK")
        trace.emit("final", text=result.text)
        trace.emit("run_end", status="completed")
    assert result.status == "done" and result.team_state["phase"] == "frozen"
    assert len(result.reports) == 2 and not result.errors
    events = read_trace(trace.path)
    assert validate(events) == []
    peer = [e for e in events if e["type"] == "team_message" and e["sender"] == "worker-2"]
    assert peer[0]["recipients"] == ["worker-1"]
    histories = contexts(events)
    for name in histories:
        requests = llm_inputs(events, name)
        for a, b in zip(requests, requests[1:]):
            assert b[:len(a)] == a
    frozen = next(e["t"] for e in events if e["type"] == "team_frozen")
    assert all(e["t"] < frozen for e in events if e["type"] == "tool_call" and e["tool"] == "work")


def test_idle_question_reactivates_same_history_with_original_grants(tmp_path):
    effects = []
    def policy(messages, tools, choice):
        used = names_used(messages)
        if messages[0]["content"].startswith("Coordinate"):
            if not used:
                return call("spawn_worker", template="worker", task="source")
            if len(team.reports) >= 1 and len(team.members) == 1:
                return call("spawn_worker", template="worker", task="ask")
            return finish_when_returned(team, messages, tools, tasks=3)
        task = json.loads(messages[1]["content"])["task"]
        mail = inbox(messages)
        if task == "source":
            if not mail:
                return {"content": "initial artifact"}
            if "write" not in used:
                return call("write")
            if "send_message" not in used:
                return call("send_message", to="worker-2", content="confirmed", reply_to=mail[0]["message_id"])
            return {"content": "clarified"}
        if not used:
            return call("send_message", to="worker-1", content="Confirm?", needs_reply=True)
        if mail:
            return {"content": "answer received"}
        return call("wait_event", timeout_seconds=0.02)
    with Trace(tmp_path / "trace.jsonl", "idle") as trace:
        team = make(trace, policy, [Tool("write", "write", {"type": "object"},
            lambda *a: effects.append(True) or Observation("ok"), budgeted=True)])
        result = team.run("root task")
    assert result.status == "done" and effects == [True]
    assert [r["cause"] for r in result.reports].count("message") == 1
    assert sum(r["usage"]["model_calls"] for r in result.reports if r["agent_id"] == "worker-1") == team.members["worker-1"].agent.model_calls
    assert not result.errors
    assert not result.infra_affected


@pytest.mark.parametrize("ceiling", [1, 2, 3, 4, 7, 12, 128])
def test_shared_ceiling_and_protected_root_final(tmp_path, ceiling):
    def policy(messages, tools, choice):
        if messages[0]["content"].startswith("Coordinate"):
            if not names_used(messages) and "spawn_worker" in tools and choice != "none":
                return {"calls": [("spawn_worker", dict(template="worker", task=str(n))) for n in range(3)]}
            if choice == "none":
                assert not any(m.active for m in team.members.values())
                return {"content": "bounded final"}
            return call("wait_event", timeout_seconds=0.01)
        return {"content": "worker final"} if choice == "none" else call("get_team_state")
    with Trace(tmp_path / "trace.jsonl", "budget") as trace:
        team = make(trace, policy, session_model_calls=ceiling)
        result = team.run("task")
    assert result.budget["model_calls"] <= ceiling
    assert len(team.client.requests) == result.budget["model_calls"]
    assert result.budget["leader_reserved_calls"] == result.budget["child_reserved_calls"] == 0
    assert not any(m.active for m in team.members.values())
    assert result.status == "done"


def invoke(agent, tool, **args):
    return agent.run_tool({"id": "test", "function": {"name": tool, "arguments": json.dumps(args)}})


def test_authority_versions_dependencies_permissions_and_messages(tmp_path):
    with Trace(tmp_path / "trace.jsonl", "authority") as trace:
        team = make(trace, lambda *a: {}, [Tool("write", "write", {"type": "object"}, lambda *a: Observation("ok"))], message_limit=2, message_bytes=4, leader_mode="coordinator")
        assert "write" not in team.leader.tools
        first = json.loads(invoke(team.leader, "spawn_worker", template="worker", task="a", write_scope="a").text)
        assert first["status"] == "queued" and not team.client.requests
        second = json.loads(invoke(team.leader, "spawn_worker", template="worker", task="b", depends_on=["task-1"], write_scope="b").text)
        worker = team.members[first["worker_id"]].agent
        assert invoke(worker, "spawn_worker", template="worker", task="bad").meta["error_kind"] == "permission_denied"
        assert invoke(team.leader, "spawn_worker", template="worker", task="overlap", write_scope="a/nested").meta["error"]
        assert invoke(team.leader, "update_task", task_id="task-1", expected_revision=9, action="accept", reason="bad").meta["error"]
        assert invoke(team.leader, "update_task", task_id="task-1", expected_revision=1, action="accept", reason="premature").meta["error"]
        assert invoke(worker, "send_message", to="nonexistent", content="hi").meta["error"]
        assert invoke(worker, "send_message", to=second["worker_id"], content="abcde").meta["error"]
        risk = json.loads(invoke(worker, "send_message", to=second["worker_id"], content="risk", kind="risk").text)
        assert risk["recipients"] == [second["worker_id"], "leader"]
        invoke(worker, "send_message", to="leader", content="info")
        assert invoke(worker, "send_message", to="leader", content="info").meta["error"]
        assert team.mail.sent == 2
        assert invoke(worker, "send_message", to="leader", content="x", reply_to="forged").meta["error"]


@pytest.mark.parametrize("status", [402, 500])
def test_worker_provider_errors_retained_without_hidden_retries(tmp_path, status):
    def policy(messages, tools, choice):
        if messages[0]["content"].startswith("Coordinate"):
            if not names_used(messages):
                return call("spawn_worker", template="worker", task="failure")
            return finish_when_returned(team, messages, tools, tasks=1)
        raise ProviderError("http_" + str(status), "fixture error", status)
    with Trace(tmp_path / "trace.jsonl", "failure") as trace:
        team = make(trace, policy)
        if status == 402:
            with pytest.raises(ProviderError) as caught:
                team.run("task")
            result = caught.value.session_outcome
        else:
            result = team.run("task")
    assert result.infra_affected and len(result.reports) == 1
    assert team.members["worker-1"].agent.model_calls == 1
    assert result.reports[0]["outcome"] == "http_" + str(status)
    assert result.budget["child_reserved_calls"] == 0
    assert result.errors[0]["agent_id"] == "worker-1"


def test_cancelled_assignment_drains_before_frozen_final(tmp_path):
    def policy(messages, tools, choice):
        if messages[0]["content"].startswith("Coordinate"):
            if not names_used(messages):
                return call("spawn_worker", template="worker", task="loop")
            if "finish_team" not in names_used(messages):
                return call("finish_team", reason="stop unfinished work")
            assert not any(m.active for m in team.members.values())
            return {"content": "unfinished preserved"}
        return {"content": "partial"} if choice == "none" else call("wait_event", timeout_seconds=120)
    with Trace(tmp_path / "trace.jsonl", "drain") as trace:
        team = make(trace, policy)
        result = team.run("task")
    assert result.status == "done" and len(result.reports) == 1
    assert result.team_state["tasks"][0]["status"] == "reported"
    assert result.team_state["close_reason"] == "stop unfinished work"


def test_dependency_runs_after_completion_without_acceptance(tmp_path):
    def policy(messages, tools, choice):
        if messages[0]["content"].startswith("Coordinate"):
            if not names_used(messages):
                return {"calls": [("spawn_worker", dict(template="worker", task="source")),
                                  ("spawn_worker", dict(template="worker", task="dependent", depends_on=["task-1"]))]}
            return finish_when_returned(team, messages, tools)
        if json.loads(messages[1]["content"])["task"] == "dependent":
            assert team.tasks["task-1"]["status"] == "reported"
        return call("finish_task", status="completed", summary="artifact produced")
    with Trace(tmp_path / "trace.jsonl", "dependency") as trace:
        team = make(trace, policy, max_parallel=1)
        result = team.run("task")
    assert len(result.reports) == 2
    assert result.team_state["tasks"][0]["status"] == "reported"


def test_reopen_preserves_history_and_lifetime_budget(tmp_path):
    def policy(messages, tools, choice):
        if messages[0]["content"].startswith("Coordinate"):
            if not names_used(messages):
                return call("spawn_worker", template="worker", task="produce")
            task = team.tasks["task-1"]
            if len(team.reports) == 1 and task["status"] == "reported":
                return call("update_task", task_id="task-1", expected_revision=task["revision"], action="reopen", reason="targeted repair")
            return finish_when_returned(team, messages, tools)
        count = sum(m["role"] == "assistant" for m in messages)
        if count % 2 == 0:
            return call("write")
        return {"content": "version " + str(count)}
    with Trace(tmp_path / "trace.jsonl", "reopen") as trace:
        team = make(trace, policy, [Tool("write", "write", {"type": "object"}, lambda *a: Observation("saved"), budgeted=True)])
        result = team.run("task")
    assert len(team.members) == 1 and len(result.reports) == 2
    assert [r["usage"]["model_calls"] for r in result.reports] == [2, 2]
    assert team.members["worker-1"].agent.budget.used == 2
    assert result.team_state["tasks"][0]["specification_revision"] == 2
    assert result.team_state["tasks"][0]["result_revision"] == 2


def test_mixed_yield_batch_and_early_submit_have_no_side_effect(tmp_path):
    from benchmarks.kramabench.adapter import make_session
    from benchmarks.kramabench.offline import FixtureWorkspace
    with Trace(tmp_path / "trace.jsonl", "submit") as trace:
        team, _ = make_session(ScriptedClient(lambda *a: {}), trace, FixtureWorkspace(tmp_path / "fixture"))
        args = dict(answer=4, pipeline_path="pipeline.py", evidence="test", unfinished=[])
        assert invoke(team.leader, "submit", **args).meta["error_kind"] == "team_admission_denied"
        assert team.leader.submission is None
        calls = [{"id": str(n), "function": {"name": name, "arguments": json.dumps(arguments)}} for n, (name, arguments)
                 in enumerate([("finish_team", {"reason": "done"}), ("spawn_worker", {"template": "worker", "task": "bad"})])]
        team.leader.answer(calls)
        assert team.phase == "open" and not team.members


def test_balance_failures_stop_paid_admission(monkeypatch):
    import httpx
    from harness import accounting
    from harness.llm import ModelConfig
    request = httpx.Request("GET", "https://example.invalid/user/balance")
    def fail(cfg):
        raise httpx.HTTPStatusError("forbidden", request=request, response=httpx.Response(403, request=request))
    monkeypatch.setattr(accounting, "balance", fail)
    observation = accounting.observed_balance(ModelConfig(model="scripted"))
    assert observation["fatal"] and observation["http_status"] == 403
    for record in (observation, {"status": "recorded", "is_available": False}):
        with pytest.raises(ValueError, match="no paid calls"):
            accounting.require_available_balance(record)


def test_utf8_quota_request_resolution_and_undelivered_receipts(tmp_path):
    from harness.messaging import Mailboxes
    with Trace(tmp_path / "trace.jsonl", "mail") as trace:
        mail = Mailboxes(trace, limit=4, max_bytes=4)
        with pytest.raises(ValueError, match="UTF-8"):
            mail.send("worker-1", "worker-2", "\u4e2d\u6587")
        request = mail.send("worker-1", "worker-2", "ask", needs_reply=True)
        with pytest.raises(ValueError, match="reply_to"):
            mail.send("worker-3", "worker-1", "yes", reply_to=request["message_id"])
        mail.resolve(request["message_id"], "leader", "cancelled")
        mail.send("worker-2", "worker-1", "late", reply_to=request["message_id"])
        assert mail.requests[request["message_id"]]["state"] == "resolved"
        assert set(mail.close("closed")) == {"worker-1", "worker-2"}


def test_tool_stop_closes_all_assistant_call_ids(tmp_path):
    from harness.agent import Agent, SessionBudget
    budget = SessionBudget()
    def fail(*args):
        raise ProviderError("http_402", "balance error", 402)
    with Trace(tmp_path / "trace.jsonl", "fatal-tools") as trace:
        trace.emit("run_start")
        actor = Agent("worker", ScriptedClient(lambda *a: {"calls": [("fail", {}), ("fail", {})]}), trace, "Worker",
                      tools=[Tool("fail", "fail", {"type": "object"}, fail)], session_budget=budget)
        with pytest.raises(ProviderError):
            actor.run("task", "report")
        trace.emit("run_end", status="error")
    assert validate(read_trace(trace.path)) == []
    assert len([m for m in actor.messages if m["role"] == "tool"]) == 2


def test_idle_send_receipt_is_explicit_and_domain_exhaustion_allows_mail(tmp_path):
    with Trace(tmp_path / "trace.jsonl", "idle-receipt") as trace:
        team = make(trace, lambda *a: {})
        for task in ("a", "b"):
            invoke(team.leader, "spawn_worker", template="worker", task=task)
        sender, receiver = team.members["worker-1"], team.members["worker-2"]
        receiver.state = "idle"
        sender.agent.budget.used = sender.agent.budget.limit
        response = json.loads(invoke(sender.agent, "send_message", to="worker-2", content="info").text)
        assert response["recipient_state"] == "idle" and response["wake_policy"] == "on_safe_boundary_if_admitted"
        assert "All messages wake idle" in response["note"]
        response = json.loads(invoke(sender.agent, "send_message", to="worker-2", content="review?", needs_reply=True).text)
        assert response["wake_policy"] == "on_safe_boundary_if_admitted"
        assert team.mail.sent == 2 and team.session_budget.snapshot()["tool_calls"] == 0


@pytest.mark.parametrize("code,answer,unfinished,accepted", [
    ("missing.py", 4, [], False), (None, 4, [], False), (None, None, [], False),
    (None, None, ["No computation completed"], True), ("pipeline.py", 4, [], True),
])
def test_team_submit_binds_exact_frozen_artifact(tmp_path, code, answer, unfinished, accepted):
    from benchmarks.kramabench.adapter import make_session
    from benchmarks.kramabench.offline import FixtureWorkspace
    with Trace(tmp_path / "trace.jsonl", "binding") as trace:
        workspace = FixtureWorkspace(tmp_path / "fixture")
        workspace.calculate({"command": "fixture_average"}, None)
        team, _ = make_session(ScriptedClient(lambda *a: {}), trace, workspace)
        with team.condition:
            team._freeze()
        observation = invoke(team.leader, "submit", answer=answer,
            pipeline_path=code, evidence="fixture", unfinished=unfinished)
        assert bool(team.leader.submission) == accepted
        assert not team.client.requests
        if not accepted:
            assert observation.meta["error_kind"] == "artifact_binding"
        else:
            assert team.submission_binding["status"] == ("exact_match" if code else "declared_unfinished")


def test_missing_or_symlink_snapshot_cannot_validate_code(tmp_path):
    import hashlib
    from benchmarks.kramabench.adapter import make_session
    from benchmarks.kramabench.offline import FixtureWorkspace
    with Trace(tmp_path / "trace.jsonl", "invalid-binding") as trace:
        team, _ = make_session(ScriptedClient(lambda *a: {}), trace, FixtureWorkspace(tmp_path / "fixture"))
        team.phase = "frozen"
        for snapshot in (None, {"files": {"fake.py": {"kind": "symlink", "sha256": hashlib.sha256(b"print(4)").hexdigest()}}}):
            team.frozen_snapshot = snapshot
            result = invoke(team.leader, "submit", answer=4, pipeline_path="fake.py", evidence="", unfinished=[])
            assert result.meta["error_kind"] == "artifact_binding" and team.leader.submission is None
        team.frozen_snapshot = {"files": {"empty.py": {"kind": "file", "sha256": hashlib.sha256(b"").hexdigest()}}}
        assert invoke(team.leader, "submit", answer=4, pipeline_path="empty.py", evidence="", unfinished=[]).meta["error"]


def test_trace_rejects_unanswered_calls_at_history_end(tmp_path):
    from harness.agent import Agent
    with Trace(tmp_path / "trace.jsonl", "broken-history") as trace:
        trace.emit("run_start")
        actor = Agent("worker", ScriptedClient(lambda *a: {}), trace, "Worker")
        actor.append({"role": "assistant", "reasoning_content": "retained", "content": "",
                      "tool_calls": [{"id": "unanswered", "function": {"name": "read", "arguments": "{}"}}]})
        trace.emit("run_end", status="error")
    assert any("history ended with unanswered" in e for e in validate(read_trace(trace.path)))


@pytest.mark.parametrize("fatal", [False, True])
def test_drain_waits_for_admitted_write_and_closes_activation(tmp_path, fatal):
    writing = threading.Event()
    effects = []
    def write(args, actor):
        writing.set()
        with team.condition:
            assert team.condition.wait_for(lambda: team.phase != "open", timeout=2)
        effects.append("admitted write finished")
        return Observation("saved artifact")
    def policy(messages, tools, choice):
        if messages[0]["content"].startswith("Coordinate"):
            if not names_used(messages):
                actions = [("spawn_worker", dict(template="worker", task="write"))]
                if fatal:
                    actions.append(("spawn_worker", dict(template="worker", task="fail")))
                return {"calls": actions}
            if not fatal and "finish_team" not in names_used(messages):
                assert writing.wait(2)
                return call("finish_team", reason="drain write")
            if fatal:
                return call("wait_event", timeout_seconds=0.02)
            assert effects == ["admitted write finished"]
            return {"content": "artifact retained"}
        task = json.loads(messages[1]["content"])["task"]
        if task == "fail":
            assert writing.wait(2)
            raise ProviderError("http_402", "fixture fatal", 402)
        return {"content": "saved artifact"} if choice == "none" else call("write")
    with Trace(tmp_path / "trace.jsonl", "inflight") as trace:
        trace.emit("run_start")
        team = make(trace, policy, [Tool("write", "write", {"type": "object"}, write, budgeted=True)])
        if fatal:
            with pytest.raises(ProviderError) as caught:
                team.run("task")
            result = caught.value.session_outcome
        else:
            result = team.run("task")
        trace.emit("run_end", status="error" if fatal else "incomplete")
    assert effects == ["admitted write finished"]
    assert len(result.reports) == (2 if fatal else 1)
    assert not any(m.active for m in team.members.values())
    assert validate(read_trace(trace.path)) == []
