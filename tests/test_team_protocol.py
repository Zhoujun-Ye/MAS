"""Team protocol and artifact-export regressions with scripted clients."""

from concurrent.futures import Future
import hashlib
import json
import os
import time

import pytest

from benchmarks.kramabench.adapter import make_session
from benchmarks.kramabench.offline import FixtureWorkspace, PIPELINE, smoke
from benchmarks.kramabench.roles import PROJECT_CONTEXT, TEMPLATES
from fakes import ScriptedClient
from harness.agent import Observation, Outcome, Tool
from harness.artifacts import MAX_ARTIFACT_BYTES, workspace_relative_path
from harness.trace import Trace, read_trace
from test_team import call, finish_when_returned, inbox, invoke, make, names_used


def test_ordinary_info_wakes_idle_member_without_changing_grants_or_task_result(tmp_path):
    writes = []
    def policy(messages, tools, choice):
        used = names_used(messages)
        if messages[0]["content"].startswith("Coordinate"):
            if not used:
                return call("spawn_worker", template="worker", task="produce")
            if len(team.reports) == 1 and "send_message" not in used:
                return call("send_message", to="worker-1", content="New information", kind="info")
            return finish_when_returned(team, messages, tools, tasks=2)
        assert "write" in tools
        if not inbox(messages):
            return {"content": "original result"}
        assert not inbox(messages)[0]["needs_reply"]
        if "write" not in used:
            return call("write")
        return {"content": "message follow-up"}
    with Trace(tmp_path / "trace.jsonl", "ordinary-info") as trace:
        team = make(trace, policy, [Tool("write", "write", {"type": "object"},
            lambda *a: writes.append(True) or Observation("saved"), budgeted=True)])
        result = team.run("root")
    assert writes == [True] and not result.errors
    assert [r["cause"] for r in result.reports] == ["assignment", "message"]
    assert team.tasks["task-1"]["report"] == "original result"
    assert team.tasks["task-1"]["result_revision"] == 1


def test_wait_has_no_implicit_timeout_and_accepts_long_explicit_timeout(tmp_path):
    with Trace(tmp_path / "trace.jsonl", "wait") as trace:
        team = make(trace, lambda *a: {})
        assert not invoke(team.leader, "wait_event").meta.get("error")
        assert team.root_waiting and team.root_deadline is None
        before = time.monotonic()
        assert not invoke(team.leader, "wait_event", timeout_seconds=180).meta.get("error")
        assert team.root_deadline >= before + 180
        assert not team.client.requests


def test_no_runnable_notification_resets_and_blocked_wakeup_restores_running(tmp_path):
    observed = []
    def policy(messages, tools, choice):
        if messages[0]["content"].startswith("Coordinate"):
            notices = [r for r in inbox(messages) if '"event": "no_runnable_work"' in r["content"]]
            if len(notices) == 1 and not team.members:
                return call("spawn_worker", template="worker", task="blocked")
            if len(notices) == 2 and "send_message" not in names_used(messages):
                return call("send_message", to="worker-1", content="prerequisite ready")
            if team.reports:
                return finish_when_returned(team, messages, tools, tasks=1)
            return call("wait_event")
        if not names_used(messages):
            return call("report_status", status="blocked", summary="Need prerequisite")
        observed.append(team.tasks["task-1"]["status"])
        return {"content": "completed after wake"}
    with Trace(tmp_path / "trace.jsonl", "blocked") as trace:
        team = make(trace, policy)
        result = team.run("root")
    assert result.status == "done" and observed == ["running"]
    notices = [e for e in read_trace(trace.path) if e["type"] == "team_message" and
               '"event": "no_runnable_work"' in e["content"]]
    assert len(notices) == 2
    assert result.budget["model_calls"] < 15


def test_batch_updates_and_absolute_write_scopes(tmp_path):
    with Trace(tmp_path / "trace.jsonl", "updates") as trace:
        team = make(trace, lambda *a: {})
        team.deadlock_notified = True
        for name in ("a", "b"):
            assert not invoke(team.leader, "spawn_worker", template="worker", task=name,
                              write_scope="/workspace/" + name).meta.get("error")
        assert [t["write_scope"] for t in team.tasks.values()] == ["a", "b"]
        assert not team.deadlock_notified
        calls = [{"id": str(i), "function": {"name": "update_task", "arguments": json.dumps(dict(
            task_id=t, expected_revision=1, action="cancel", reason="cancel batch"))}}
            for i, t in enumerate(team.tasks)]
        team.leader.answer(calls)
        assert all(t["status"] == "cancelled" for t in team.tasks.values())
        assert not team.leader.tool_events


def test_finite_wait_is_bounded_by_session_deadline_without_model_polling(tmp_path):
    with Trace(tmp_path / "trace.jsonl", "deadline") as trace:
        team = make(trace, lambda *a: call("wait_event", timeout_seconds=5))
        team.session_budget.seconds = 0.1
        result = team.run("root")
    assert result.status == "incomplete" and result.leader_status == "session_time_limit"
    assert result.budget["model_calls"] == 1


def test_progress_clears_prior_blocked_task_state(tmp_path):
    with Trace(tmp_path / "trace.jsonl", "progress") as trace:
        team = make(trace, lambda *a: {})
        invoke(team.leader, "spawn_worker", template="worker", task="work")
        member = team.members["worker-1"]
        with team.condition:
            team._activate(member, "assignment")
        invoke(member.agent, "report_status", status="blocked", summary="waiting")
        assert team.tasks["task-1"]["status"] == "blocked"
        invoke(member.agent, "report_status", status="progress", summary="working")
        assert team.tasks["task-1"]["status"] == "running"


def test_forced_handoff_is_partial_not_dependency_completion(tmp_path):
    with Trace(tmp_path / "trace.jsonl", "partial") as trace:
        team = make(trace, lambda *a: {})
        invoke(team.leader, "spawn_worker", template="worker", task="source")
        member = team.members["worker-1"]
        with team.condition:
            team._activate(member, "assignment")
            member.agent.last_call_final = True
            member.agent.last_final_reason = "turn_limit"
            future = Future()
            future.set_result(Outcome("unfinished", "done", 2))
            team._complete("worker-1", future)
        assert team.tasks["task-1"]["outcome"] == "partial"
        assert team.reports[0]["final_reason"] == "turn_limit"


def test_freeze_waits_for_full_tool_leader_inflight_write(tmp_path):
    writes = []
    def write(args, actor):
        with team.condition:
            assert team.condition.wait_for(lambda: team.phase != "open", timeout=2)
            assert team.phase == "draining"
        writes.append(True)
        return Observation("saved")
    def policy(messages, tools, choice):
        if messages[0]["content"].startswith("Coordinate"):
            if not names_used(messages):
                return {"calls": [("spawn_worker", dict(template="worker", task="consume capacity")), ("write", {})]}
            assert writes == [True] and team.phase == "frozen"
            return {"content": "closed"}
        return {"content": "partial"} if choice == "none" else call("get_team_state")
    with Trace(tmp_path / "trace.jsonl", "leader-write") as trace:
        team = make(trace, policy, [Tool("write", "write", {"type": "object"}, write, budgeted=True)],
                    session_model_calls=4, leader_mode="full")
        result = team.run("root")
    assert result.status == "done" and writes == [True]
    events = read_trace(trace.path)
    write_done = next(e["t"] for e in events if e["type"] == "tool_call" and e["tool"] == "write")
    freeze = next(e["t"] for e in events if e["type"] == "team_frozen")
    assert write_done < freeze


@pytest.mark.parametrize("leader_mode", ["full", "coordinator"])
def test_fixed_templates_inherit_global_limits_and_neutral_project_context(tmp_path, leader_mode):
    with Trace(tmp_path / "trace.jsonl", "templates") as trace:
        team, _ = make_session(ScriptedClient(lambda *a: {}), trace, FixtureWorkspace(tmp_path / "fixture"),
                              leader_mode=leader_mode, session_model_calls=64, session_tool_calls=120)
        for template in TEMPLATES:
            assert template.max_turns is None and template.tool_budget is None
            invoke(team.leader, "spawn_worker", template=template.name, task="local brief")
        assert ("terminal" in team.leader.tools) == (leader_mode == "full")
        assert ("write_file" in team.leader.tools) == (leader_mode == "full")
        for actor in [team.leader, *(m.agent for m in team.members.values())]:
            assert actor.max_turns == 64 and actor.budget.limit == 120
            system = actor.messages[0]["content"]
            assert PROJECT_CONTEXT in system
            for removed in ("ANALYSIS_CONTRACT", "PRIMARY estimand", "64", "120", "Check units", "unverified interpretation"):
                assert removed not in system
        explorer = team.members["worker-2"].agent
        assert "terminal" in explorer.tools and "write_file" not in explorer.tools
        assert "not a technical sandbox" in explorer.messages[0]["content"]


@pytest.mark.parametrize("path", ["x.py", "/workspace/x.py", "dir/x.py", "/workspace/dir/x.py"])
def test_workspace_paths_normalize(path):
    assert workspace_relative_path(path) == path.removeprefix("/workspace/")


@pytest.mark.parametrize("path", ["/data/x.py", "/workspace/../x.py", "../x.py", ".", "/workspace", "", "x\x00.py"])
def test_unsafe_workspace_paths_rejected(path):
    with pytest.raises(ValueError):
        workspace_relative_path(path)


@pytest.mark.parametrize("mode,leader_mode", [("single", "full"), ("team", "full"), ("team", "coordinator")])
def test_single_and_both_team_modes_export_exact_file_with_same_contract(tmp_path, mode, leader_mode):
    with Trace(tmp_path / "trace.jsonl", "artifact") as trace:
        workspace = FixtureWorkspace(tmp_path / "fixture")
        workspace.calculate({"command": "fixture_average"}, None)
        session, _ = make_session(ScriptedClient(lambda *a: {}), trace, workspace, mode=mode, leader_mode=leader_mode)
        if mode == "team":
            with session.condition:
                session._freeze()
        response = invoke(session.leader, "submit", answer=4, pipeline_path="/workspace/pipeline.py", evidence="fixture", unfinished=[])
        assert not response.meta.get("error")
        assert json.loads(session.leader.submission)["pipeline_code"] == PIPELINE
        assert session.submission_binding["pipeline_code_sha256"] == hashlib.sha256(PIPELINE.encode()).hexdigest()
        assert session.submission_binding["pipeline_path"] == "pipeline.py"
        assert session.session_budget.snapshot()["tool_calls"] == 0 and not session.client.requests
        assert not session.submission_binding["trusted_pipeline_reexecution"]


@pytest.mark.parametrize("case", ["symlink", "parent_symlink", "fifo", "large", "stale", "invalid_utf8", "empty"])
def test_bounded_export_refuses_unsafe_or_changed_file(tmp_path, case):
    workspace = FixtureWorkspace(tmp_path / "fixture")
    content = b"print(4)\n"
    target = workspace.work / "pipeline.py"
    target.write_bytes(content)
    path = "pipeline.py"
    digest = hashlib.sha256(content).hexdigest()
    if case == "symlink":
        (workspace.work / "link.py").symlink_to(target)
        path = "link.py"
    elif case == "parent_symlink":
        (workspace.work / "link").symlink_to(workspace.work, target_is_directory=True)
        path = "link/pipeline.py"
    elif case == "fifo":
        os.mkfifo(workspace.work / "pipe")
        path = "pipe"
    elif case == "large":
        target.write_bytes(b"x" * (MAX_ARTIFACT_BYTES + 1))
    elif case == "stale":
        target.write_bytes(b"print(5)\n")
    elif case in {"invalid_utf8", "empty"}:
        content = b"\xff" if case == "invalid_utf8" else b" \n"
        target.write_bytes(content)
        digest = hashlib.sha256(content).hexdigest()
    with pytest.raises(ValueError):
        workspace.export_artifact(path, digest)


@pytest.mark.parametrize("mode", ["single", "team"])
def test_inline_code_is_not_a_submission_fallback(tmp_path, mode):
    with Trace(tmp_path / "trace.jsonl", "legacy-submit") as trace:
        session, _ = make_session(ScriptedClient(lambda *a: {}), trace, FixtureWorkspace(tmp_path / "fixture"), mode=mode)
        response = invoke(session.leader, "submit", answer=4, pipeline_code=PIPELINE, evidence="fixture", unfinished=[])
        assert response.meta["error"] and session.leader.submission is None


def test_export_transport_failure_is_infrastructure_affected(tmp_path, monkeypatch):
    with Trace(tmp_path / "trace.jsonl", "export-failure") as trace:
        workspace = FixtureWorkspace(tmp_path / "fixture")
        workspace.calculate({"command": "fixture_average"}, None)
        def fail(*args, **kwargs):
            raise RuntimeError("fixture transport failure")
        monkeypatch.setattr(workspace, "export_artifact", fail)
        session, _ = make_session(ScriptedClient(lambda *a: {}), trace, workspace, mode="single")
        response = invoke(session.leader, "submit", answer=4, pipeline_path="pipeline.py", evidence="fixture", unfinished=[])
        assert response.meta["error_kind"] == "artifact_export_transport"
        assert session.infra_affected and session.leader.submission is None


@pytest.mark.parametrize("leader_mode", ["full", "coordinator"])
def test_scripted_team_smoke_records_arm_and_artifact_contract(tmp_path, leader_mode):
    output = tmp_path / "smoke"
    response = smoke(output, leader_mode=leader_mode)
    manifest = json.loads((output / "attempt" / "manifest.json").read_text())
    report = json.loads((output / "attempt" / "report.json").read_text())
    assert response["explanation"]["answer"] == 4
    assert manifest["team_arm"] == ("full_tool_leader" if leader_mode == "full" else "coordinator_only")
    assert manifest["output_contract"]["artifact_policy"] == "selected_path_frozen_hash_v3"
    assert report["artifact_binding"]["status"] == "exact_match"
    assert report["integrity_errors"] == [] and not report["infra_affected"]
