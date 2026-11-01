import json
import subprocess
import threading

import pytest

from fakes import ScriptedClient
from harness.agent import Observation, Tool
from harness.llm import ProviderError
from harness.subagents import CHILD_REPORT_POLICY, DELEGATION_POLICY, LeaderSubagent, SubagentTemplate, comparison_session
from harness.trace import Trace, read_trace, validate
from harness.workspace_audit import GitWorkspaceAudit


def batch_policy(child):
    def policy(messages, tools, choice):
        if "delegate" in tools:
            if choice == "none":
                return {"content": "final report"}
            if not any(m["role"] == "tool" for m in messages):
                return {"calls": [("delegate", {"template": "worker", "task": task}) for task in ("one", "two")]}
            return {"content": "combined"}
        return child(messages, tools, choice)
    return policy


def test_parallel_briefs_audits_and_ordered_results(tmp_path):
    barrier = threading.Barrier(2)
    def child(messages, tools, choice):
        assert "ORIGINAL SECRET" not in json.dumps(messages)
        assert CHILD_REPORT_POLICY in messages[0]["content"]
        assert "Invocation model-call limit" in messages[0]["content"]
        barrier.wait(timeout=5)
        return {"content": json.loads(messages[-1]["content"])["task"]}
    with Trace(tmp_path / "trace.jsonl", "parallel") as trace:
        trace.emit("run_start")
        session = LeaderSubagent(ScriptedClient(batch_policy(child)), trace,
                                [SubagentTemplate("worker", "Work", "Worker")], max_parallel=2,
                                workspace_audit=lambda: {"audit_only_secret": "not model-visible"})
        result = session.run("ORIGINAL SECRET")
        assert result.status == "done"
        assert result.budget["model_calls"] == 4
        reports = [json.loads(m["content"]) for m in session.leader.messages if m["role"] == "tool"]
        assert [r["report"] for r in reports] == ["one", "two"]
        assert len(session.children) == 2
        assert "audit_only_secret" not in json.dumps(session.leader.messages)
        trace.emit("final", text=result.text)
        trace.emit("run_end", status="completed")
    events = read_trace(trace.path)
    assert validate(events) == []
    snapshots = [e for e in events if e["type"] == "workspace_snapshot"]
    assert len(snapshots) == 4
    assert {e["invocation"] for e in snapshots} == {1, 2}
    assert all(e["attribution"] == "shared_interval_not_exclusive" for e in snapshots)


def test_shared_call_limit_is_atomic(tmp_path):
    client = ScriptedClient(batch_policy(lambda *args: {"content": "done"}))
    with Trace(tmp_path / "trace.jsonl", "limited") as trace:
        session = LeaderSubagent(client, trace, [SubagentTemplate("worker", "Work", "Worker")],
                                max_parallel=2, session_model_calls=2)
        result = session.run("task")
        assert result.status == "done"
        assert result.leader_status == "done"
        assert len(client.requests) == result.budget["model_calls"] == 2
        assert all(r.get("error_kind") == "report_reservation_unavailable" for r in result.delegations)
        assert not session.children


def test_parallel_tools_share_budget(tmp_path):
    hits = []
    barrier = threading.Barrier(2)
    def child(messages, tools, choice):
        if messages[-1]["role"] == "user":
            barrier.wait(timeout=5)
            return {"calls": [("read", {})]}
        return {"content": "report"}
    tool = Tool("read", "Read", {"type": "object"},
                lambda args, agent: (hits.append(agent.name) or Observation("read")), budgeted=True)
    with Trace(tmp_path / "trace.jsonl", "tools") as trace:
        session = LeaderSubagent(ScriptedClient(batch_policy(child)), trace,
                                [SubagentTemplate("worker", "Work", "Worker", ("read",))], [tool],
                                session_tool_calls=1)
        result = session.run("task")
        assert result.status == "done"
        assert len(hits) == result.budget["tool_calls"] == 1
        assert any(e["error_kind"] == "budget_exhausted" for e in result.tool_events)


def test_same_child_cannot_run_twice_at_once(tmp_path):
    entered, release = threading.Event(), threading.Event()
    def policy(*args):
        entered.set()
        assert release.wait(timeout=5)
        return {"content": "done"}
    with Trace(tmp_path / "trace.jsonl", "resume") as trace:
        session = LeaderSubagent(ScriptedClient(policy), trace, [SubagentTemplate("worker", "Work", "Worker")])
        args = {"template": "worker", "task": "work"}
        thread = threading.Thread(target=session._delegate, args=(args, None))
        thread.start()
        try:
            assert entered.wait(timeout=5)
            denied = session._delegate(dict(args, resume_id="subagent-1"), None)
            assert denied.meta["error_kind"] == "child_busy"
            assert session.delegations == 1
        finally:
            release.set()
            thread.join(timeout=5)
        assert not thread.is_alive()
        assert session.child_status["subagent-1"] == "completed"


@pytest.mark.parametrize("kind,affected", [("http", True), ("context_length", False)])
def test_infrastructure_marker_is_separate_from_lifecycle(tmp_path, kind, affected):
    def child(*args):
        raise ProviderError(kind, "scripted")
    with Trace(tmp_path / "trace.jsonl", "infra") as trace:
        session = LeaderSubagent(ScriptedClient(batch_policy(child)), trace,
                                [SubagentTemplate("worker", "Work", "Worker")])
        result = session.run("task")
        assert result.status == "done"
        assert result.infra_affected is affected
        assert len(result.errors) == 2


def test_comparison_grants_and_budget_are_explicit(tmp_path):
    tool = Tool("read", "Read", {"type": "object"}, lambda *args: Observation("ok"), budgeted=True)
    prompts = []
    for delegated in (False, True):
        with Trace(tmp_path / f"{delegated}.jsonl", "comparison") as trace:
            session = comparison_session(ScriptedClient(lambda *args: {"content": "done"}), trace,
                                         [SubagentTemplate("worker", "Work", "Worker", ("read",))], [tool],
                                         delegated=delegated, domain_tools=("read",),
                                         session_model_calls=12, session_tool_calls=9)
            assert set(session.leader.tools) == ({"read", "delegate"} if delegated else {"read"})
            assert session.session_budget.model_limit == 12
            assert session.session_budget.tool_limit == 9
            prompts.append(session.leader.messages[0]["content"])
    assert "Subagents:" not in prompts[0]
    assert DELEGATION_POLICY not in prompts[0]
    assert DELEGATION_POLICY in prompts[1]
    assert prompts[0].split("\nSession")[0] == prompts[1].split(DELEGATION_POLICY)[0]


def test_workspace_snapshot_tracks_changes_and_untracked(tmp_path):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)
    git("init")
    (tmp_path / "file.txt").write_text("before")
    git("add", "file.txt")
    git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "base")
    audit = GitWorkspaceAudit(tmp_path)
    before = audit()
    (tmp_path / "file.txt").write_text("after")
    (tmp_path / "new.txt").write_text("new")
    after = audit()
    assert before["files"]["file.txt"]["sha256"] != after["files"]["file.txt"]["sha256"]
    assert "new.txt" in after["files"]
    assert before["diff_sha256"] != after["diff_sha256"]
    assert not after["atomic"]


def test_audit_failure_is_visible_without_prompt_pollution(tmp_path):
    def audit():
        raise OSError("audit unavailable")
    with Trace(tmp_path / "trace.jsonl", "audit") as trace:
        session = LeaderSubagent(ScriptedClient(batch_policy(lambda *args: {"content": "done"})), trace,
                                [SubagentTemplate("worker", "Work", "Worker")], workspace_audit=audit)
        result = session.run("task")
        assert result.infra_affected
        assert "audit unavailable" not in json.dumps(session.leader.messages)
    assert len([e for e in read_trace(trace.path) if e["type"] == "workspace_audit_error"]) == 4


def test_corrected_arguments_and_resume_are_normal_reports(tmp_path):
    hits = []
    def policy(messages, tools, choice):
        if "delegate" in tools:
            count = sum(m["role"] == "tool" for m in messages)
            if count == 2:
                return {"content": "final"}
            args = {"template": "worker", "task": "local task"}
            if count:
                args["resume_id"] = "subagent-1"
            return {"calls": [("delegate", args)]}
        observations = [m for m in messages if m["role"] == "tool"]
        if not observations:
            return {"calls": [("read", {"unexpected": True})]}
        if len(observations) == 1:
            return {"calls": [("read", {})]}
        return {"content": "verified report"}
    tool = Tool("read", "Read", {"type": "object", "additionalProperties": False},
                lambda *args: (hits.append(True) or Observation("evidence")), budgeted=True)
    with Trace(tmp_path / "trace.jsonl", "recovery") as trace:
        session = LeaderSubagent(ScriptedClient(policy), trace,
                                [SubagentTemplate("worker", "Work", "Worker", ("read",))], [tool])
        result = session.run("task")
        assert result.status == "done"
        assert [r["status"] for r in result.delegations] == ["completed", "completed"]
        assert len(result.errors) == 1
        assert result.errors[0]["error_kind"] == "invalid_arguments"
        assert len(hits) == result.budget["tool_calls"] == 1
        assert not result.infra_affected
