"""Offline regressions for shared-budget feedback and task admission."""

from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
import json

import pytest

from harness.agent import Outcome, SessionBudget
from harness.trace import Trace, llm_inputs, read_trace, validate
from test_team import call, finish_when_returned, invoke, make, names_used


def returned_member(team):
    invoke(team.leader, "spawn_worker", template="worker", task="produce")
    member = team.members["worker-1"]
    with team.condition:
        team._activate(member, "assignment")
        member.declaration = dict(status="completed", summary="saved artifact")
        future = Future()
        future.set_result(Outcome("saved artifact", "done", 0))
        team._complete(member.agent.name, future)
    return member


@pytest.mark.parametrize("operation", ["spawn", "assign", "reopen"])
@pytest.mark.parametrize("limit", ["model", "activation"])
def test_preflight_rejects_without_mutating_assignments(tmp_path, operation, limit):
    with Trace(tmp_path / "trace.jsonl", "preflight") as trace:
        team = make(trace, lambda *a: {})
        member = returned_member(team)
        if limit == "model":
            while team.session_budget.snapshot()["model_calls_unreserved"] > 1:
                team.session_budget.take_model("leader")
        else:
            team.max_activations = team.activations
        tasks = deepcopy(team.tasks)
        history = deepcopy(member.agent.messages)
        budget = team.session_budget.snapshot()
        if operation == "spawn":
            result = invoke(team.leader, "spawn_worker", template="worker", task="extra")
        elif operation == "assign":
            result = invoke(team.leader, "assign_task", worker_id="worker-1", task="extra")
        else:
            result = invoke(team.leader, "update_task", task_id="task-1",
                            expected_revision=team.tasks["task-1"]["revision"], action="reopen", reason="repair")
        receipt = json.loads(result.text)
        assert result.meta["error_kind"] == "team_admission_denied"
        assert receipt["status"] == "rejected"
        assert not receipt["admission"]["can_start"]
        assert receipt["reason"] == ("model_capacity" if limit == "model" else "activation_limit")
        assert receipt["budget"]["model_calls"] == budget["model_calls"]
        assert receipt["admission"]["required_unreserved_calls"] == 2
        assert team.tasks == tasks and list(team.members) == ["worker-1"]
        assert member.state == "idle" and member.agent.messages == history
        assert team.session_budget.snapshot()["leader_reserved_calls"] == 1
        assert not team.client.requests
        # Capacity checks do not prevent accepting/cancelling old work.
        accepted = invoke(team.leader, "update_task", task_id="task-1",
                          expected_revision=team.tasks["task-1"]["revision"], action="accept", reason="retain")
        assert not accepted.meta.get("error")
        cancelled = invoke(team.leader, "update_task", task_id="task-1",
                           expected_revision=team.tasks["task-1"]["revision"], action="cancel", reason="superseded")
        assert not cancelled.meta.get("error")


def test_capacity_probe_is_advisory_and_reservations_remain_atomic():
    budget = SessionBudget(model_calls=3)
    before = budget.snapshot()
    with ThreadPoolExecutor(4) as pool:
        probes = list(pool.map(lambda _: budget.report_capacity(require_work=True), range(4)))
        admitted = list(pool.map(lambda i: budget.reserve_report(str(i), require_work=True), range(4)))
    assert all(p["can_start"] for p in probes)
    assert sum(admitted) == 1
    assert before["model_calls"] == budget.snapshot()["model_calls"] == 0
    assert budget.snapshot()["leader_reserved_calls"] == 1
    assert not budget.report_capacity(require_work=True)["can_start"]


def test_queued_work_is_rechecked_after_concurrent_consumption(tmp_path):
    with Trace(tmp_path / "trace.jsonl", "late-capacity") as trace:
        team = make(trace, lambda *a: {}, session_model_calls=5)
        for task in ("one", "two"):
            receipt = json.loads(invoke(team.leader, "spawn_worker", template="worker", task=task).text)
            assert receipt["status"] == "queued"
            assert receipt["budget"]["child_reserved_calls"] == 0
        with team.condition:
            team._activate(team.members["worker-1"], "assignment")
            team.session_budget.take_model("worker-1")
            team.session_budget.take_model("worker-1")
            team._activate(team.members["worker-2"], "assignment")
        assert team.members["worker-2"].state == "exhausted"
        assert team.tasks["task-2"]["status"] == "assigned"
        assert team.activations == 1
        assert team.session_budget.snapshot()["leader_reserved_calls"] == 1
        notice = json.loads(list(team.mail.records.values())[-1]["content"])
        assert notice["event"] == "activation_rejected"
        assert notice["budget"]["model_calls_unreserved"] == 1


def test_dependency_queue_and_control_receipts_preserve_current_budget(tmp_path):
    with Trace(tmp_path / "trace.jsonl", "dependency-budget") as trace:
        team = make(trace, lambda *a: {})
        returned_member(team)
        receipt = json.loads(invoke(team.leader, "assign_task", worker_id="worker-1", task="next").text)
        assert receipt["status"] == "queued" and "budget" in receipt
        receipt = json.loads(invoke(team.leader, "spawn_worker", template="worker", task="dependent",
                                    depends_on=["task-2"]).text)
        assert receipt["status"] == "queued"
        assert not team._assignment_ready(team.members["worker-2"])
        assert receipt["budget"]["child_reserved_calls"] == 0


@pytest.mark.parametrize("leader_mode", ["coordinator", "full"])
def test_leader_turns_and_handoffs_refresh_budget_without_extra_calls(tmp_path, leader_mode):
    def policy(messages, tools, choice):
        if messages[0]["content"].startswith("Coordinate"):
            notices = [m for m in messages if m["role"] == "user" and m["content"].startswith("Team budget before")]
            budget = json.loads(notices[-1]["content"].split("\n", 1)[1])
            assert "wall_seconds" not in budget
            assert budget["model_calls"] < team.session_budget.snapshot()["model_calls"]
            if not names_used(messages):
                return call("spawn_worker", template="worker", task="produce")
            if not team.reports:
                return call("wait_event")
            assert budget["model_calls"] >= team.reports[-1]["budget"]["model_calls"]
            return finish_when_returned(team, messages, tools, tasks=1)
        if len(names_used(messages)) < 8:
            return call("get_team_state")
        return call("finish_task", status="completed", summary="saved artifact; interpretation remains uncertain")

    with Trace(tmp_path / "trace.jsonl", "live-budget") as trace:
        trace.emit("run_start")
        team = make(trace, policy, session_model_calls=128, leader_mode=leader_mode)
        result = team.run("private task")
        trace.emit("final", text=result.text)
        trace.emit("run_end", status="completed")
    assert not result.errors and not result.infra_affected
    assert result.budget["model_calls"] == len(team.client.requests) < 128
    assert result.reports[0]["budget"]["child_reserved_calls"] == 0
    assert result.reports[0]["budget"]["leader_reserved_calls"] == 1
    assert result.reports[0]["usage"]["model_calls"] == 9
    events = read_trace(trace.path)
    assert validate(events) == []
    requests = llm_inputs(events, "leader")
    for index, messages in enumerate(requests, 1):
        assert sum(m["role"] == "user" and m["content"].startswith("Team budget before") for m in messages) == index
    for previous, current in zip(requests, requests[1:]):
        assert current[:len(previous)] == previous


def test_pilot_uses_paper_informed_ceiling_with_no_retries():
    from scripts.kramabench import pilot
    assert pilot.LIMITS["session_model_calls"] == 600
    assert pilot.LIMITS["session_tool_calls"] == 300
    assert pilot.LIMITS["session_seconds"] == 3600
    assert pilot.LIMITS["worker_quantum"] == 16
    assert pilot.MODEL.retries == 0
