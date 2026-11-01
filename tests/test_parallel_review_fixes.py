import json
import re
import subprocess
import threading

import pytest

from fakes import ScriptedClient
from harness.agent import Observation, SessionBudget, SessionLimit, Tool
from harness.execution import ContainerWorkspace
from harness.llm import ProviderError
from harness.subagents import LeaderSubagent, SubagentTemplate
from harness.trace import Trace, read_trace
from harness.workspace_audit import GitWorkspaceAudit


def test_default_budget_keeps_leader_final_call(tmp_path):
    def policy(messages, tools, choice):
        if choice == "none":
            return {"content": "final report"}
        if "delegate" in tools:
            return {"calls": [("delegate", {"template": "worker", "task": str(i)}) for i in range(2)]}
        return {"calls": [("read", {})]}
    tool = Tool("read", "Read", {"type": "object"}, lambda *args: Observation("ok"), budgeted=True)
    with Trace(tmp_path / "trace.jsonl", "reserve") as trace:
        client = ScriptedClient(policy)
        session = LeaderSubagent(client, trace, [SubagentTemplate("worker", "Work", "Worker", ("read",))], [tool])
        result = session.run("task")
        assert result.text == "final report"
        assert result.status == "done"
        assert len(client.requests) == result.budget["model_calls"] == 40
        assert client.requests[-1][2] == "none"
        assert "reserved final session call" in client.requests[-1][0][-1]["content"]


def test_unbudgeted_tool_stops_after_preflight(tmp_path):
    entered, stopped = threading.Event(), threading.Event()
    effects = []
    def preflight(args, agent):
        entered.set()
        assert stopped.wait(5)
    def policy(messages, tools, choice):
        if "delegate" in tools:
            return {"calls": [("delegate", {"template": "worker", "task": task}) for task in ("slow", "fatal")]}
        task = json.loads(messages[-1]["content"])["task"]
        if task == "fatal":
            assert entered.wait(5)
            raise ProviderError("http", "balance", 402)
        return {"calls": [("write", {})]}
    tool = Tool("write", "Write", {"type": "object"},
                lambda *args: (effects.append(True) or Observation("written")), preflight=preflight)
    with Trace(tmp_path / "trace.jsonl", "preflight") as trace:
        session = LeaderSubagent(ScriptedClient(policy), trace,
                                [SubagentTemplate("worker", "Work", "Worker", ("write",))], [tool])
        original = session.session_budget.stop
        def stop(error):
            original(error)
            stopped.set()
        session.session_budget.stop = stop
        with pytest.raises(ProviderError) as failure:
            session.run("task")
        statuses = failure.value.session_outcome.child_statuses
        assert statuses == {"subagent-1": "stopped_after_fatal", "subagent-2": "provider_error"}
        assert not effects


def test_ids_follow_call_order_despite_reverse_admission(tmp_path):
    second_done = threading.Event()
    def policy(messages, tools, choice):
        if "delegate" in tools:
            if messages[-1]["role"] == "user":
                return {"calls": [("delegate", {"template": "worker", "task": task}) for task in ("first", "second")]}
            return {"content": "done"}
        return {"content": json.loads(messages[-1]["content"])["task"]}
    with Trace(tmp_path / "trace.jsonl", "ids") as trace:
        session = LeaderSubagent(ScriptedClient(policy), trace, [SubagentTemplate("worker", "Work", "Worker")])
        original = session.leader.tools["delegate"].run
        def delayed(args, agent):
            if args["task"] == "first":
                assert second_done.wait(5)
            result = original(args, agent)
            if args["task"] == "second":
                second_done.set()
            return result
        session.leader.tools["delegate"].run = delayed
        result = session.run("task")
        assert {r["report"]: r["agent_id"] for r in result.delegations} == {
            "first": "subagent-1", "second": "subagent-2"}
    events = read_trace(trace.path)
    starts = {e["invocation"]: e for e in events if e["type"] == "delegation_start"}
    ends = {e["invocation"]: e for e in events if e["type"] == "delegation_end"}
    assert starts.keys() == ends.keys()
    for key in starts:
        assert starts[key]["call_id"] == ends[key]["call_id"]
        assert starts[key]["agent"] == ends[key]["agent_id"]


def test_git_receipts_include_head_refs_and_ignore_optional_lock(tmp_path):
    def git(*args):
        return subprocess.run(["git", *args], cwd=tmp_path, capture_output=True, check=True)
    git("init")
    (tmp_path / "file").write_text("same bytes")
    git("add", "file")
    git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "base")
    audit = GitWorkspaceAudit(tmp_path)
    before = audit()
    git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "--allow-empty", "-m", "new")
    git("branch", "audit-branch")
    (tmp_path / ".git" / "index.lock").write_text("held by another process")
    after = audit()
    assert after["optional_locks"] is False
    assert before["files"] == after["files"]
    assert before["head"] != after["head"]
    assert before["refs"] != after["refs"]
    assert after["refs"]["refs/heads/audit-branch"] == after["head"]


def test_container_audit_capture_is_independent_of_model_limit(monkeypatch):
    payload = json.dumps({"head": "abc", "refs": {}, "files": {
        f"file-{i}": {"sha256": "a" * 64} for i in range(1000)}}).encode()
    def run(argv, **kwargs):
        marker = re.search(r"__command_exit_[0-9a-f]+:", argv[-3]).group()
        assert "GIT_OPTIONAL_LOCKS=0" in argv[-1]
        kwargs["stdout"].write(payload + b"\n" + marker.encode() + b"0\n")
        return subprocess.CompletedProcess(argv, 0)
    monkeypatch.setattr(subprocess, "run", run)
    workspace = ContainerWorkspace("fixture", output_limit=30000)
    assert len(payload) > workspace.output_limit
    assert len(workspace.audit_snapshot()["files"]) == 1000
    assert workspace.output_limit == 30000


def test_deadline_rejects_new_dispatch_and_late_reports(tmp_path, monkeypatch):
    now = [0.0]
    monkeypatch.setattr("harness.agent.time.monotonic", lambda: now[0])
    def policy(*args):
        now[0] = 11.0
        return {"content": "too late"}
    with Trace(tmp_path / "trace.jsonl", "deadline") as trace:
        client = ScriptedClient(policy)
        session = LeaderSubagent(client, trace, [], session_seconds=10)
        result = session.run("task")
        assert result.status == "incomplete"
        assert result.leader_status == "session_time_limit"
        with pytest.raises(SessionLimit, match="session_time_limit"):
            session.session_budget.admit_tool()
        assert len(client.requests) == 1


def test_budget_denials_identify_scope():
    from harness.agent import Budget
    shared = SessionBudget(tool_calls=0)
    assert shared.admit_tool(Budget(3)) == "session_tool_limit"
    shared = SessionBudget(tool_calls=3)
    assert shared.admit_tool(Budget(0)) == "agent_tool_limit"
    assert shared.snapshot()["tool_calls"] == 0


def test_real_client_receives_remaining_timeout_without_network(tmp_path, monkeypatch):
    import httpx
    from harness.llm import ChatClient, ModelConfig
    received = []
    def handler(request):
        received.append(request.extensions["timeout"])
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {
            "role": "assistant", "content": "report", "reasoning_content": ""}}], "usage": {}})
    client = ChatClient(ModelConfig(model="offline-mock", timeout=900), transport=httpx.MockTransport(handler))
    with Trace(tmp_path / "trace.jsonl", "timeout") as trace:
        session = LeaderSubagent(client, trace, [], session_seconds=10)
        assert session.run("task").status == "done"
        assert 0 < received[0]["read"] <= 10
    client._http.close()


def test_resume_reports_pair_with_their_audit_intervals(tmp_path):
    def policy(messages, tools, choice):
        if "delegate" not in tools:
            return {"content": "same report"}
        count = sum(m["role"] == "tool" for m in messages)
        if count == 2:
            return {"content": "done"}
        args = {"template": "worker", "task": "local"}
        if count:
            args["resume_id"] = "subagent-1"
        return {"calls": [("delegate", args)]}
    with Trace(tmp_path / "trace.jsonl", "resume") as trace:
        session = LeaderSubagent(ScriptedClient(policy), trace, [SubagentTemplate("worker", "Work", "Worker")],
                                workspace_audit=lambda: {"snapshot": "receipt"})
        result = session.run("task")
    events = read_trace(trace.path)
    for report in result.delegations:
        invocation = report["invocation"]
        starts = [e for e in events if e["type"] == "delegation_start" and e["invocation"] == invocation]
        ends = [e for e in events if e["type"] == "delegation_end" and e["invocation"] == invocation]
        audits = [e for e in events if e["type"] == "workspace_snapshot" and e["invocation"] == invocation]
        assert len(starts) == len(ends) == 1
        assert starts[0]["call_id"] == ends[0]["call_id"] == report["call_id"]
        assert [e["phase"] for e in audits] == ["before", "after"]
        assert starts[0]["t"] < audits[0]["t"] < audits[1]["t"] < ends[0]["t"]


def test_expired_session_skips_audit_without_calling_hook(tmp_path, monkeypatch):
    now = [0.0]
    monkeypatch.setattr("harness.agent.time.monotonic", lambda: now[0])
    with Trace(tmp_path / "trace.jsonl", "deadline-audit") as trace:
        session = LeaderSubagent(ScriptedClient(lambda *args: {"content": "done"}), trace, [],
                                workspace_audit=lambda: pytest.fail("must not start after deadline"), session_seconds=2)
        session.session_budget.start()
        now[0] = 3.0
        session._audit("after", "subagent-1", 1)
    assert read_trace(trace.path)[-1]["type"] == "workspace_audit_skipped"
