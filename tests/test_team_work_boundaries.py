"""Scripted work-boundary regressions, with no paid or network execution."""

from concurrent.futures import Future
import json

import pytest

from harness.agent import Outcome, Observation, Tool
from harness.trace import Trace, read_trace, validate, llm_inputs
from test_team import call, finish_when_returned, inbox, invoke, make, names_used
from test_team_budget_feedback import returned_member


def complete_step(team, member, result):
    future = Future()
    future.set_result(result)
    with team.condition:
        team._complete(member.agent.name, future)


@pytest.mark.parametrize("paused", [False, True])
def test_assignment_queues_behind_message_without_history_or_scope_race(tmp_path, paused):
    with Trace(tmp_path / "trace.jsonl", "atomic-brief") as trace:
        team = make(trace, lambda *a: {})
        member = returned_member(team)
        old_task = member.task_id
        invoke(team.leader, "send_message", to=member.agent.name, content="Framing only", action="none")
        with team.condition:
            team._activate(member, "message")
        if paused:
            member.state = "checkpoint"
        before = list(member.agent.messages)
        result = invoke(team.leader, "assign_task", worker_id=member.agent.name,
                        task="next step", context="Entire new local brief", deliverable="saved result",
                        stop_condition="run once, record output", write_scope=team.tasks[old_task]["write_scope"])
        assert not result.meta.get("error")
        assert json.loads(result.text)["queued_behind_message"]
        assert member.agent.messages == before and member.active
        assert member.pending_task_id == "task-2"
        assert team.tasks[old_task]["status"] == "reported"
        assert team.tasks["task-2"]["status"] == "assigned"
        assert not team._assignment_ready(member)
        assert invoke(team.leader, "assign_task", worker_id=member.agent.name, task="duplicate").meta["error"]
        complete_step(team, member, Outcome("FYI handled", "done", 1))
        assert team.reports[-1]["task_id"] is None
        assert team.reports[-1]["previous_task_id"] == old_task
        assert team.reports[-1]["pending_task_id"] == "task-2"
        assert team._assignment_ready(member)
        with team.condition:
            team._activate(member, "assignment")
        brief = json.loads(member.agent.messages[-1]["content"])
        assert brief["context"] == "Entire new local brief"
        assert brief["stop_condition"] == "run once, record output"


def test_message_actions_validated_before_sending_and_no_action_finishes_in_one_call(tmp_path):
    effects = []
    def policy(messages, tools, choice):
        if messages[0]["content"].startswith("Coordinate"):
            used = names_used(messages)
            if not used:
                return call("spawn_worker", template="worker", task="initial")
            if team.reports and "send_message" not in used:
                return call("send_message", to="worker-1", content="No action or reply needed", action="none")
            return finish_when_returned(team, messages, tools, tasks=2)
        if inbox(messages):
            assert inbox(messages)[-1]["action"] == "none"
            assert "write" in tools
            assert "For action=none" in json.dumps(messages)
            return call("finish_message", summary="FYI received; no work needed")
        return call("finish_task", status="completed", summary="initial done")
    with Trace(tmp_path / "trace.jsonl", "message-boundary") as trace:
        team = make(trace, policy, [Tool("write", "write", {"type": "object"},
                    lambda *a: effects.append(True) or Observation("ok"))])
        result = team.run("root")
        assert not result.errors and not effects
        assert result.reports[-1]["cause"] == "message"
        assert result.reports[-1]["usage"]["model_calls"] == 1
        assert result.reports[-1]["completion_status"] is None
    with Trace(tmp_path / "bad.jsonl", "bad-message") as trace:
        team = make(trace, lambda *a: {})
        returned_member(team)
        count = team.mail.sent
        obs = invoke(team.leader, "send_message", to="worker-1", content="Do everything", action="work")
        assert obs.meta["error"] and team.mail.sent == count
        obs = invoke(team.leader, "send_message", to="worker-1", content="One check", action="work",
                     expected_result="observed output", stop_condition="one execution")
        assert not obs.meta.get("error")
        record = list(team.mail.records.values())[-1]
        assert record["stop_condition"] == "one execution"


@pytest.mark.parametrize("leader_mode", ["coordinator", "full"])
def test_automatic_checkpoint_retains_activation_and_requires_leader_decision(tmp_path, leader_mode):
    observed = []
    def policy(messages, tools, choice):
        if messages[0]["content"].startswith("Coordinate"):
            if not names_used(messages):
                return {"calls": [("spawn_worker", dict(template="worker", task="producer")),
                                  ("spawn_worker", dict(template="worker", task="dependent", depends_on=["task-1"]))]}
            member = team.members["worker-1"]
            if member.state == "checkpoint":
                observed.append(member.activation)
                assert team.tasks["task-1"]["result_revision"] == 0
                assert team.tasks["task-2"]["status"] == "assigned"
                assert team.session_budget.snapshot()["child_reserved_calls"] == 1
                return call("continue_worker", worker_id="worker-1", instruction="Stop checking; finish with observed evidence")
            return finish_when_returned(team, messages, tools)
        task = json.loads(messages[1]["content"])["task"]
        if task == "producer" and len(names_used(messages)) < 2:
            return call("get_team_state")
        return call("finish_task", status="completed", summary="bounded work done")
    with Trace(tmp_path / "trace.jsonl", "quantum") as trace:
        trace.emit("run_start")
        team = make(trace, policy, worker_quantum=2, leader_mode=leader_mode, session_model_calls=128)
        result = team.run("private root")
        trace.emit("final", text=result.text)
        trace.emit("run_end", status="completed")
    assert observed == [1] and not result.errors
    assert len(result.reports) == 2 and result.reports[0]["usage"]["model_calls"] == 3
    assert team.activations == 2 and result.budget["model_calls"] == len(team.client.requests) <= 128
    events = read_trace(trace.path)
    assert validate(events) == []
    for agent in ("worker-1", "leader"):
        requests = llm_inputs(events, agent)
        for previous, current in zip(requests, requests[1:]):
            assert current[:len(previous)] == previous


@pytest.mark.parametrize("cancel", [False, True])
def test_checkpoint_can_be_closed_or_cancelled_without_waiting_forever(tmp_path, cancel):
    def policy(messages, tools, choice):
        if messages[0]["content"].startswith("Coordinate"):
            if not names_used(messages):
                return call("spawn_worker", template="worker", task="long")
            if team.members["worker-1"].state == "checkpoint":
                if cancel:
                    task = team.tasks["task-1"]
                    return call("update_task", task_id="task-1", expected_revision=task["revision"], action="cancel", reason="stop")
                return call("finish_team", reason="retain partial work")
            return finish_when_returned(team, messages, tools, tasks=1)
        return {"content": "partial work retained"} if choice == "none" else call("get_team_state")
    with Trace(tmp_path / "trace.jsonl", "checkpoint-stop") as trace:
        team = make(trace, policy, worker_quantum=1)
        result = team.run("root")
    assert not result.errors and result.status == "done"
    assert result.reports[0]["outcome"] == "partial"
    assert not team.members["worker-1"].active
    assert result.budget["child_reserved_calls"] == 0


def test_voluntary_checkpoint_waits_until_tool_turn_finishes(tmp_path):
    with Trace(tmp_path / "trace.jsonl", "explicit-checkpoint") as trace:
        team = make(trace, lambda *a: call("report_status", status="checkpoint", summary="saved file; run it next"))
        returned_member(team)
        invoke(team.leader, "assign_task", worker_id="worker-1", task="bounded follow-up")
        member = team.members["worker-1"]
        with team.condition:
            team._activate(member, "assignment")
        result = team._step(member.agent.name)
        assert member.state != "checkpoint"
        complete_step(team, member, result)
        assert member.state == "checkpoint" and member.agent.model_calls == 1
        assert not invoke(team.leader, "continue_worker", worker_id=member.agent.name, instruction="Run only the saved file").meta.get("error")
        assert member.state == "ready" and member.activation == 2


def test_mail_for_checkpointed_member_is_not_a_false_progress_source(tmp_path):
    def policy(messages, tools, choice):
        if messages[0]["content"].startswith("Coordinate"):
            used = names_used(messages)
            if not used:
                return call("spawn_worker", template="worker", task="long work")
            if team.phase == "frozen":
                return {"content": "partial evidence retained"}
            if team.members["worker-1"].state == "checkpoint" and "send_message" not in used:
                return call("send_message", to="worker-1", content="FYI only", action="none")
            return call("wait_event")
        return {"content": "partial report"} if choice == "none" else call("get_team_state")
    with Trace(tmp_path / "trace.jsonl", "paused-mail") as trace:
        team = make(trace, policy, worker_quantum=1)
        result = team.run("root")
    assert not result.errors and result.status == "done"
    assert result.team_state["close_reason"] == "no_runnable_work"
    assert result.budget["model_calls"] < 15
