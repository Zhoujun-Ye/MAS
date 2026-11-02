"""Explicit claims, dependency-waiting mail and matched Leader conditions."""

import copy
from concurrent.futures import Future
import json
from types import SimpleNamespace

import pytest

from benchmarks.kramabench.offline import comparison_smoke
from harness.agent import Observation, Outcome, Tool
from harness.comparison import selected_conditions, validate_pair
from harness.trace import Trace, activation_summary, read_trace, validate
from test_comparison_review_fixes import paired_specs
from test_team import call, finish_when_returned, inbox, invoke, make, names_used


@pytest.mark.parametrize("claim", [None, "completed", "partial", "blocked", "failed"])
def test_only_explicit_completed_claim_releases_dependency(tmp_path, claim):
    def policy(messages, tools, choice):
        if messages[0]["content"].startswith("Coordinate"):
            if not names_used(messages):
                return {"calls": [("spawn_worker", dict(template="worker", task="source")),
                                  ("spawn_worker", dict(template="worker", task="dependent", depends_on=["task-1"]))]}
            if team.phase == "frozen":
                return {"content": "final"}
            if team.tasks["task-1"]["status"] == "reported":
                task = team.tasks["task-1"]
                return call("update_task", task_id=task["task_id"], expected_revision=task["revision"], action="accept", reason="Record receipt, not verified correctness")
            if len(team.reports) == (2 if claim == "completed" else 1):
                return call("finish_team", reason="Claims recorded")
            return call("wait_event")
        if choice == "none":
            return {"content": "forced partial"}
        task = json.loads(messages[1]["content"])["task"]
        if task == "source" and claim is None:
            return {"content": "Analysis completed, but pipeline not executed and result unverified"}
        return call("finish_task", status=claim if task == "source" else "completed", summary="Scoped member claim only")
    with Trace(tmp_path / "trace.jsonl", "claims") as trace:
        trace.emit("run_start")
        team = make(trace, policy)
        result = team.run("root")
        trace.emit("final", text=result.text)
        trace.emit("run_end", status="completed")
    assert result.status == "done" and not result.errors and not result.infra_affected
    assert team.tasks["task-1"]["outcome"] == "done"
    assert team.tasks["task-1"]["completion_status"] == (claim or "unclaimed")
    assert team.tasks["task-2"]["result_revision"] == int(claim == "completed")
    assert team.tasks["task-1"]["status"] == "accepted"
    assert validate(read_trace(trace.path)) == []


def test_pending_dependency_member_handles_mail_without_starting_task(tmp_path):
    effects = []
    def policy(messages, tools, choice):
        if messages[0]["content"].startswith("Coordinate"):
            if not names_used(messages):
                return {"calls": [("spawn_worker", dict(template="worker", task="source")),
                                  ("spawn_worker", dict(template="worker", task="dependent", context="LOCAL_INTERFACE_BRIEF", depends_on=["task-1"]))]}
            return finish_when_returned(team, messages, tools, tasks=3)
        if messages[1]["content"].startswith("Message activation"):
            member = team.members["worker-2"]
            if member.cause == "message":
                assert "LOCAL_INTERFACE_BRIEF" in messages[1]["content"]
                assert team.tasks["task-2"]["status"] == "assigned"
                assert team.tasks["task-2"]["result_revision"] == 0
                assert "work" in tools
                if "work" not in names_used(messages):
                    return call("work")
                if "send_message" not in names_used(messages):
                    question = next(r for r in inbox(messages) if r["needs_reply"])
                    return call("send_message", to="worker-1", content="Interface agreed", reply_to=question["message_id"])
                return {"content": "Message answered; pending task has not run"}
            assert team.tasks["task-1"]["completion_status"] == "completed"
            return call("finish_task", status="completed", summary="Dependent assignment completed")
        if "send_message" not in names_used(messages):
            return call("send_message", to="worker-2", content="Need interface before finishing", needs_reply=True, task_id="task-1")
        if not any(r["kind"] == "info" and r["sender"] == "worker-2" for r in inbox(messages)):
            return call("wait_event")
        return call("finish_task", status="completed", summary="Source completed using peer interface")
    with Trace(tmp_path / "trace.jsonl", "pending-mail") as trace:
        trace.emit("run_start")
        team = make(trace, policy, [Tool("work", "work", {"type": "object"},
                    lambda *a: effects.append(True) or Observation("checked interface"), budgeted=True)], max_parallel=1)
        result = team.run("ROOT_ONLY")
        trace.emit("final", text=result.text)
        trace.emit("run_end", status="completed")
    assert result.status == "done" and not result.errors and effects == [True]
    assert team.tasks["task-2"]["result_revision"] == 1
    assert len(team.reports) == 3
    events = read_trace(trace.path)
    assert validate(events) == []
    stats = activation_summary(events)
    message = next(r for r in stats["activations"] if r["cause"] == "message")
    assert message["pending_task_id"] == "task-2" and message["task_id"] is None and message["previous_task_id"] is None
    assert message["trigger_messages"][0]["sender"] == "worker-1"
    assert message["trigger_messages"][0]["task_id"] == "task-1"
    assert message["trigger_message_ids"] == message["exposed_message_ids"]
    assert message["domain_tool_calls"] == 1 and message["domain_actions"][0]["tool"] == "work"
    assert message["workspace_changes"] is None
    assert not any(e["type"] == "team_stall_resolution" for e in events)


def test_claim_controls_reject_message_cancelled_and_mixed_use(tmp_path):
    with Trace(tmp_path / "trace.jsonl", "claim-gates") as trace:
        team = make(trace, lambda *a: {})
        invoke(team.leader, "spawn_worker", template="worker", task="a")
        member = team.members["worker-1"]
        with team.condition:
            team._activate(member, "assignment")
        calls = [{"id": str(i), "function": {"name": name, "arguments": json.dumps(args)}} for i, (name, args) in
                 enumerate([("finish_task", dict(status="completed", summary="bad batch")), ("get_team_state", {})])]
        member.agent.answer(calls)
        assert member.declaration is None
        member.cause = "message"
        assert invoke(member.agent, "finish_task", status="completed", summary="cannot finish pending task").meta["error"]
        member.cause = "assignment"
        invoke(team.leader, "update_task", task_id="task-1", expected_revision=team.tasks["task-1"]["revision"], action="cancel", reason="cancel")
        assert invoke(member.agent, "finish_task", status="completed", summary="late").meta["error"]
        assert member.declaration is None


def test_pending_message_does_not_count_as_consumed_dependency_and_cancel_does_not_restart(tmp_path):
    with Trace(tmp_path / "trace.jsonl", "pending-cancel") as trace:
        team = make(trace, lambda *a: {})
        invoke(team.leader, "spawn_worker", template="worker", task="a")
        invoke(team.leader, "spawn_worker", template="worker", task="b", depends_on=["task-1"])
        source, dependent = team.members.values()
        with team.condition:
            team._activate(source, "assignment")
            source.declaration = dict(status="partial", summary="needs repair")
            ended = Future()
            ended.set_result(Outcome("needs repair", "done", 1))
            team._complete("worker-1", ended)
            invoke(team.leader, "send_message", to="worker-2", content="Interface question")
            team._activate(dependent, "message")
        task = team.tasks["task-1"]
        assert not invoke(team.leader, "update_task", task_id="task-1", expected_revision=task["revision"], action="reopen", reason="repair").meta.get("error")
        assert task["completion_status"] is None and task["specification_revision"] == 2
        task = team.tasks["task-2"]
        invoke(team.leader, "update_task", task_id="task-2", expected_revision=task["revision"], action="cancel", reason="not needed")
        with team.condition:
            ended = Future()
            ended.set_result(Outcome("reply", "done", 1))
            team._complete("worker-2", ended)
        assert dependent.state == "idle" and task["status"] == "cancelled" and task["result_revision"] == 0


def test_activation_file_deltas_are_shared_intervals_not_exclusive_writes():
    events = [
        dict(type="team_activation_start", agent="worker-1", activation=1, cause="message", t=1),
        dict(type="workspace_snapshot", agent="worker-1", activation=1, phase="before", snapshot={"files": {}}, t=2),
        dict(type="team_activation_start", agent="worker-2", activation=2, cause="assignment", t=3),
        dict(type="tool_call", agent="leader", tool="write_file", call_id="root-write", budget_charged=True, t=4),
        dict(type="workspace_snapshot", agent="worker-1", activation=1, phase="after", snapshot={"files": {"other.py": {"kind": "file", "sha256": "new"}}}, t=5),
        dict(type="team_activation_end", agent_id="worker-1", outcome="done", completion_status=None, t=6),
        dict(type="team_activation_end", agent_id="worker-2", outcome="done", completion_status="completed", t=7),
    ]
    stats = activation_summary(events)
    assert stats["activations"][0]["workspace_changes"][0]["path"] == "other.py"
    assert stats["activations"][0]["domain_tool_calls"] == 0
    assert stats["activations"][0]["overlapping_activations"] == [2]
    assert stats["activations"][0]["audit_events"] == {"before": 2, "after": 5}
    assert stats["leader_domain_tool_calls"] == 1
    assert stats["activations"][1]["workspace_changes"] is None
    assert "not semantic production" in stats["interpretation"]


def test_leader_pair_requires_matching_contract_and_exact_conditions(tmp_path):
    old = paired_specs(tmp_path)
    conditions = selected_conditions("leader-pair")
    arms = {name: dict(spec, condition=condition) for (name, condition), spec in zip(conditions.items(), old.values())}
    assert validate_pair(arms)["contrast"] == "leader_permissions"
    wrong = copy.deepcopy(arms)
    wrong["team_full"]["condition"]["leader_mode"] = "coordinator"
    with pytest.raises(ValueError, match="requires coordinator and full"):
        validate_pair(wrong)
    wrong = copy.deepcopy(arms)
    wrong["team_full"]["contract"]["budgets"] = "more"
    with pytest.raises(ValueError, match="contract differs"):
        validate_pair(wrong)
    for mode, setting in [("leader-pair", "full"), ("single", "coordinator"), ("team", "unknown")]:
        with pytest.raises(ValueError):
            selected_conditions(mode, setting)
    assert list(selected_conditions("team")) == ["team"]


def test_scripted_leader_pair_has_same_nonpermission_contract(tmp_path):
    result = comparison_smoke(tmp_path / "pair", leader_pair=True)
    assert result["status"] == "completed" and result["order"] == ["team_coordinator", "team_full"]
    coord, full = (result["arms"][key] for key in result["order"])
    assert coord["leader_domain_tools"] == [] and "terminal" in full["leader_domain_tools"]
    assert coord["team_arm"] == "coordinator_only" and full["team_arm"] == "full_tool_leader"
    assert not coord["integrity_errors"] and not full["integrity_errors"]
    for arm in (coord, full):
        assert not arm["infra_affected"] and arm["activation_usage"]["activations"][0]["completion_status"] == "completed"


@pytest.mark.parametrize("leader_mode", ["coordinator", "full"])
def test_same_coordination_policy_with_enforced_different_domain_grants(tmp_path, leader_mode):
    with Trace(tmp_path / "trace.jsonl", "permissions") as trace:
        effects = []
        team = make(trace, lambda *a: {}, [Tool("work", "work", {"type": "object"},
                    lambda *a: effects.append(True) or Observation("done"), budgeted=True)], leader_mode=leader_mode)
        result = invoke(team.leader, "work")
        assert effects == ([True] if leader_mode == "full" else [])
        assert bool(result.meta.get("error")) == (leader_mode == "coordinator")
        assert "Prioritize organizing collaboration" in team.leader.messages[0]["content"]
        assert "meaningful multi-member decomposition" in team.leader.messages[0]["content"]


@pytest.mark.parametrize("fatal", [False, True])
def test_pilot_leader_pair_dispatch_is_explicit_once_per_arm_and_stops_after_fatal(tmp_path, monkeypatch, fatal):
    from benchmarks.kramabench.tasks import Task
    from harness.llm import ProviderError
    from scripts.kramabench import pilot
    upstream = tmp_path / "upstream"
    (upstream / "data/archeology/input").mkdir(parents=True)
    (tmp_path / ".env").touch(mode=0o600)
    root = tmp_path / "run"
    conditions = selected_conditions("leader-pair")
    calls, created, removed, closed = [], [], [], []

    class Client:
        def __init__(self, cfg):
            assert cfg.retries == 0
            self._http = SimpleNamespace(close=lambda: closed.append(True))

    class Workspace:
        def __init__(self, container, archive_dir):
            self.container, self.archive_dir = container, archive_dir
        def execute(self, command):
            return dict(execution_error=False, exit_code=0, output="synthetic probe")
        def audit_snapshot(self):
            return {"fixture_only": True, "files": {}}
        def tools(self):
            return ()

    def command(args, **kwargs):
        assert args[:2] == ["docker", "run"] and args[args.index("--pull") + 1] == "never"
        identifier = "fixture-container-" + str(len(created))
        created.append(identifier)
        return identifier + "\n"

    def run_command(args, **kwargs):
        assert args[:2] in (["git", "init"], ["docker", "rm"])
        if args[0] == "docker":
            removed.append(args[-1])
        return SimpleNamespace(returncode=0, stderr="")

    def environment(workspace, dataset, output):
        return dict(image_id="fixture-image", container_id=workspace.container, dataset_files={"values": "hash"},
                    resources={"Memory": 100}, network="none", mounts=[
                        {"Destination": "/data", "Source": str(dataset)},
                        {"Destination": "/workspace", "Source": str(root / "workspaces" / output.name)}])

    def attempt(task, **kwargs):
        name = kwargs["output"].name
        calls.append(dict(name=name, mode=kwargs["mode"], leader_mode=kwargs["leader_mode"],
                          model_calls=kwargs["session_model_calls"], comparison=kwargs["comparison_sha256"]))
        if fatal:
            raise ProviderError("http_402", "synthetic balance failure", 402)
        kwargs["output"].mkdir()
        pilot.write_json(kwargs["output"] / "report.json", dict(status="completed", fixture_only=True))

    monkeypatch.setattr(pilot, "ROOT", tmp_path)
    monkeypatch.setattr(pilot, "load_env", lambda: None)
    monkeypatch.setattr(pilot, "load_tasks", lambda path: ([Task("fixture", "archeology", "public fixture")], {}))
    monkeypatch.setattr(pilot, "ChatClient", Client)
    monkeypatch.setattr(pilot, "ContainerWorkspace", Workspace)
    monkeypatch.setattr(pilot, "inspection_tools", lambda ws: ())
    monkeypatch.setattr(pilot, "catalog_manifest", lambda *a: {"fixture": True})
    monkeypatch.setattr(pilot, "validate_data_container", environment)
    monkeypatch.setattr(pilot, "observed_balance", lambda cfg: {"status": "recorded", "is_available": True})
    monkeypatch.setattr(pilot, "run_task", attempt)
    monkeypatch.setattr(pilot.subprocess, "check_output", command)
    monkeypatch.setattr(pilot.subprocess, "run", run_command)
    monkeypatch.setattr(pilot.sys, "argv", ["pilot", "--upstream", str(upstream), "--image", "fixture-image",
        "--output", str(root), "--task-id", "fixture", "--mode", "leader-pair", "--execute-paid"])
    pilot.main()
    assert [c["name"] for c in calls] == (["team_coordinator"] if fatal else list(conditions))
    for record in calls:
        assert {k: record[k] for k in ("mode", "leader_mode")} == conditions[record["name"]]
        assert record["model_calls"] == 64
    assert removed == created and len(closed) == 2
    summary = json.loads((root / "summary.json").read_text())
    assert summary["conditions"] == conditions and summary["paid_judge_calls"] == 0
    if fatal:
        assert summary["status"] == "stopped_after_fatal"
        assert summary["arms"]["team_full"]["status"] == "not_run_after_fatal"
    else:
        assert len({c["comparison"] for c in calls}) == 1
