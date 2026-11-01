"""Prompt wiring and scripted workflow checks, not measured model efficiency."""

import csv
import json
import threading
from collections import Counter

from benchmarks.kramabench.adapter import make_session, parse_submission
from benchmarks.kramabench.offline import FixtureWorkspace
from benchmarks.kramabench.roles import DELEGATION_GUIDANCE, TEMPLATES
from harness.agent import Observation
from harness.subagents import CHILD_SCOPE_POLICY, DELEGATION_POLICY, LeaderSubagent, SubagentTemplate
from harness.trace import Trace, contexts, read_trace, validate
from tests.fakes import ScriptedClient


def test_scope_policy_is_generic_mas_only_and_child_prefix_is_stable(tmp_path):
    client = ScriptedClient(lambda *args: {"content": "Local findings."})
    template = SubagentTemplate("reader", "Read local evidence.", "Read only the assigned evidence.")
    with Trace(tmp_path / "generic.jsonl", "generic") as trace:
        session = LeaderSubagent(client, trace, [template])
        assert DELEGATION_POLICY in session.leader.messages[0]["content"]
        for local in ("LOCAL_A", "LOCAL_B"):
            session._delegate({"template": "reader", "task": local}, None)
        first, second = session.children.values()
        assert first.messages[0] == second.messages[0]
        assert CHILD_SCOPE_POLICY in first.messages[0]["content"]
        assert "LOCAL_A" not in first.messages[0]["content"]
        assert "independent check" in DELEGATION_POLICY
        assert "assign ownership early" in DELEGATION_POLICY
        assert "one owner per deliverable" in DELEGATION_POLICY
        assert "foreground runtime waits" in DELEGATION_POLICY
        assert "Small or tightly coupled work" in DELEGATION_POLICY
        assert "implement, run and validate" in CHILD_SCOPE_POLICY
        assert "missing, conflicting" in DELEGATION_POLICY
        assert "recompute" in CHILD_SCOPE_POLICY
        workspace = FixtureWorkspace(tmp_path / "fixture")
        single, _ = make_session(client, trace, workspace, mode="single")
        mas, _ = make_session(client, trace, workspace, mode="mas")
        assert DELEGATION_POLICY not in single.leader.messages[0]["content"]
        assert DELEGATION_GUIDANCE not in single.leader.messages[0]["content"]
        assert DELEGATION_POLICY in mas.leader.messages[0]["content"]
        assert DELEGATION_GUIDANCE in mas.leader.messages[0]["content"]
        assert single.leader.response_format == mas.leader.response_format
        assert single.session_budget.snapshot() == mas.session_budget.snapshot()
    assert "same-method" in DELEGATION_GUIDANCE
    assert "scout's broad inventory" in next(t.system for t in TEMPLATES if t.name == "requirement_analyst")
    assert "supplied inventory" in next(t.system for t in TEMPLATES if t.name == "data_scout")


def test_scoped_parallel_checks_allow_raw_recomputation_and_targeted_repair_resume(tmp_path, monkeypatch):
    import httpx
    def forbid_network(*args, **kwargs):
        raise AssertionError("No network")
    monkeypatch.setattr(httpx.Client, "send", forbid_network)
    workspace = FixtureWorkspace(tmp_path / "fixture")
    pipeline = workspace.work / "pipeline.py"
    pipeline.write_text("print(sum(values) / 2)\n")
    corrected = "print(sum(values) / len(values))\n"
    actions = Counter()
    barrier = threading.Barrier(2)
    original_tools = workspace.tools

    def toolset():
        tools = original_tools()
        def read(args, agent):
            assert args["path"] == "/workspace/pipeline.py"
            actions[(agent.name, "read")] += 1
            return Observation(pipeline.read_text())
        def compute(args, agent):
            assert args["command"] in {"independent_fixture_mean", "verify_repaired_fixture"}
            # Fixed trusted calculation from raw data, not execution of model code.
            with (workspace.data / "values.csv").open() as stream:
                values = [float(row["value"]) for row in csv.DictReader(stream)]
            if args["command"] == "verify_repaired_fixture":
                assert pipeline.read_text() == corrected
            actions[(agent.name, "compute")] += 1
            return Observation(json.dumps({"mean": sum(values) / len(values), "rows": len(values)}))
        def repair(args, agent):
            assert agent.name == "leader" and args == {"path": "/workspace/pipeline.py", "content": corrected}
            pipeline.write_text(corrected)
            actions[(agent.name, "repair")] += 1
            return Observation("Changed divisor; recheck the changed calculation.")
        for tool in tools:
            if tool.name in {"read_file", "terminal", "write_file"}:
                tool.run = {"read_file": read, "terminal": compute, "write_file": repair}[tool.name]
        return tools
    workspace.tools = toolset
    root_turn = 0

    def policy(messages, tools, choice):
        nonlocal root_turn
        if "delegate" in tools:
            root_turn += 1
            if root_turn == 1:
                return {"calls": [("delegate", {"template": "result_reviewer",
                    "task": "Check only the divisor in /workspace/pipeline.py; source has 3 rows. Do not inventory files.",
                    "context": "Known paths: /data/values.csv, /workspace/pipeline.py. Estimand: sample mean."}),
                    ("delegate", {"template": "reproduction_checker",
                    "task": "Independently compute the sample mean from /data/values.csv. Do not read the candidate pipeline or inventory files. Write only /workspace/repro if needed.",
                    "context": "Known schema: one value column. Raw source supplied; answer intentionally withheld."})]}
            if root_turn == 2:
                assert any("incorrect divisor" in m["content"] for m in messages if m["role"] == "tool")
                return {"calls": [("write_file", {"path": "/workspace/pipeline.py", "content": corrected})]}
            if root_turn == 3:
                return {"calls": [("delegate", {"template": "reproduction_checker", "resume_id": "subagent-2",
                    "task": "Divisor repaired in /workspace/pipeline.py. Recheck only that changed calculation against your prior raw-data result; do not restart discovery."})]}
            return {"calls": [("submit", {"answer": 4, "pipeline_code": corrected,
                "evidence": "Scripted independent arithmetic check and targeted repair verification.", "unfinished": []})]}
        assert "ROOT_ONLY_SENTINEL" not in json.dumps(messages)
        assert CHILD_SCOPE_POLICY in messages[0]["content"]
        if messages[-1]["role"] == "user":
            resumed = any(m["role"] == "assistant" for m in messages)
            if not resumed:
                barrier.wait(timeout=10)
            if "terminal" in tools:
                return {"calls": [("terminal", {"command": "verify_repaired_fixture" if resumed else "independent_fixture_mean"})]}
            return {"calls": [("read_file", {"path": "/workspace/pipeline.py"})]}
        return {"content": messages[-1]["content"] if "terminal" in tools else "Confirmed incorrect divisor: 2 instead of 3."}

    client = ScriptedClient(policy)
    with Trace(tmp_path / "trace.jsonl", "scope") as trace:
        trace.emit("run_start")
        session, _ = make_session(client, trace, workspace)
        outcome = session.run("Check supplied artifacts. ROOT_ONLY_SENTINEL: candidate answer 6.")
        assert parse_submission(outcome.text)["answer"] == 4
        assert outcome.status == "done" and not outcome.errors and not outcome.infra_affected
        assert len(session.children) == 2 and session.delegations == 3
        assert session.children["subagent-2"].budget.used == 2
        assert pipeline.read_text() == corrected
        trace.emit("final", text=outcome.text)
        trace.emit("run_end", status="completed")
    events = read_trace(tmp_path / "trace.jsonl")
    assert validate(events) == []
    assert actions == {("subagent-1", "read"): 1, ("subagent-2", "compute"): 2, ("leader", "repair"): 1}
    assert not any(e["type"] == "tool_call" and e["tool"] in {"list_files", "inspect_file"} for e in events)
    history = contexts(events)["subagent-2"]
    assert len([m for m in history if m["role"] == "tool"]) == 2
    assert "candidate answer 6" not in json.dumps(history)
