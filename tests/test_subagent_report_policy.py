"""Soft report guidance must never become hidden compaction or a new tool grant."""

from copy import deepcopy
import json

import pytest

from harness.agent import Observation, Tool
from harness.subagents import CHILD_REPORT_POLICY, DELEGATION_POLICY, LeaderSubagent, SubagentTemplate
from harness.trace import Trace, contexts, read_trace, validate
from tests.fakes import ScriptedClient


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import httpx
    def forbid(*args, **kwargs):
        raise AssertionError("No network or paid model calls")
    monkeypatch.setattr(httpx.Client, "send", forbid)


def test_final_message_baseline_has_no_section_schema_or_word_target():
    assert "concise natural-language summary" in CHILD_REPORT_POLICY
    assert "Choose the format and length appropriate to the task" in CHILD_REPORT_POLICY
    for policy in (CHILD_REPORT_POLICY, DELEGATION_POLICY):
        assert "150-250" not in policy
        assert "Conclusion, Evidence, Impact, Unfinished" not in policy
        assert "four compact sections" not in policy


def test_long_report_is_not_cut_and_resume_keeps_full_history(tmp_path):
    raw = "RAW_TOOL_ONLY " + "row data\n" * 2000
    long_report = "Conclusion: material findings.\nEvidence: source rows 1-2000.\n" + "important finding " * 2000
    long_report += "\nImpact: review needed.\nUnfinished: LAST_BLOCKER_MUST_SURVIVE"
    delta = "Source row 2 confirms the prior finding; the blocker remains unresolved."
    saved = []
    tool = Tool("read", "Read evidence", {"type": "object"}, lambda *a: Observation(raw),
                budgeted=True, read_only=True)

    def policy(messages, tools, choice):
        if "delegate" in tools:
            reports = [json.loads(m["content"]) for m in messages if m["role"] == "tool"]
            assert "RAW_TOOL_ONLY" not in json.dumps(messages)
            assert "CHILD_PRIVATE_REASONING" not in json.dumps(messages)
            if not reports:
                return {"calls": [("delegate", {"template": "reader", "task": "Read evidence; report blockers."})]}
            assert reports[0]["report"] == long_report
            if len(reports) == 1:
                return {"calls": [("delegate", {"template": "reader", "resume_id": "subagent-1",
                                                "task": "Clarify row 2 only."})]}
            assert reports[1]["report"] == delta
            return {"content": "Integrated."}
        assert CHILD_REPORT_POLICY in messages[0]["content"]
        if not any(m["role"] == "assistant" for m in messages):
            return {"calls": [("read", {})], "reasoning": "CHILD_PRIVATE_REASONING"}
        if messages[-1]["role"] == "tool":
            assert messages[-1]["content"] == raw
            saved.extend(deepcopy(messages))
            return {"content": long_report, "reasoning": "CHILD_PRIVATE_REASONING final"}
        assert messages[:len(saved)] == saved
        assert messages[-2]["content"] == long_report
        assert messages[-2]["reasoning_content"] == "CHILD_PRIVATE_REASONING final"
        return {"content": delta}

    client = ScriptedClient(policy)
    with Trace(tmp_path / "trace.jsonl", "reports") as trace:
        trace.emit("run_start")
        session = LeaderSubagent(client, trace, [SubagentTemplate("reader", "Read", "Reader", ("read",))], [tool])
        result = session.run("Resolve findings.")
        assert result.status == "done" and not result.errors
        assert result.budget["model_calls"] == len(client.requests) == 6
        assert session.children["subagent-1"].budget.used == 1
        trace.emit("final", text=result.text)
        trace.emit("run_end", status="completed")
    events = read_trace(tmp_path / "trace.jsonl")
    assert validate(events) == []
    assert [e["report"] for e in events if e["type"] == "delegation_end"] == [long_report, delta]
    histories = contexts(events)
    assert raw in [m["content"] for m in histories["subagent-1"] if m["role"] == "tool"]
    assert long_report in [m["content"] for m in histories["subagent-1"] if m["role"] == "assistant"]


@pytest.mark.parametrize("writable", [False, True])
def test_summary_references_details_without_granting_storage_or_loading_details(tmp_path, writable):
    source = tmp_path / "source.csv"
    source.write_text("PRIVATE_DETAIL_COLUMN\n" + "2\n" * 1000)
    artifact = tmp_path / "details.csv"
    operations = []
    def save(args, agent):
        operations.append("save")
        artifact.write_text(source.read_text())
        return Observation("Saved details.csv")
    def read(args, agent):
        operations.append("read")
        return Observation(source.read_text())
    tools = [Tool("save", "Persist assigned detail", {"type": "object"}, save, budgeted=True),
             Tool("read", "Read source", {"type": "object"}, read, budgeted=True, read_only=True)]
    grant = "save" if writable else "read"
    evidence = "details.csv, rows 1-1001" if writable else "source.csv, rows 1-1001; no new file saved (read-only)"
    summary = f"Values inspected in {evidence}; no issue found within this scope."

    def policy(messages, names, choice):
        if "delegate" in names:
            if messages[-1]["role"] == "user":
                return {"calls": [("delegate", {"template": "worker", "task": "Inspect source.csv; assigned output is details.csv if writing is permitted."})]}
            assert json.loads(messages[-1]["content"])["report"] == summary
            assert "PRIVATE_DETAIL_COLUMN" not in json.dumps(messages)
            return {"content": "Integrated evidence location."}
        assert names == [grant]
        assert "only when your granted tools permit writing" in messages[0]["content"]
        if messages[-1]["role"] == "user":
            return {"calls": [(grant, {})]}
        return {"content": summary}

    client = ScriptedClient(policy)
    with Trace(tmp_path / "trace.jsonl", "storage") as trace:
        session = LeaderSubagent(client, trace, [SubagentTemplate("worker", "Check", "Worker", (grant,))], tools)
        result = session.run("Inspect evidence.")
        assert result.status == "done" and not result.errors
        assert result.budget["model_calls"] == len(client.requests) == 4
        assert result.budget["tool_calls"] == 1
    assert operations == [grant]
    assert artifact.exists() == writable
    if writable:
        assert artifact.read_text() == source.read_text()


@pytest.mark.parametrize("finish,expected", [("stop", "completed"), ("length", "partial")])
def test_forced_final_uses_summary_guidance_without_saving_or_repair_calls(tmp_path, finish, expected):
    text = "Inspection of source.csv:2 is incomplete; details have not been saved."
    def final(messages, choice):
        assert choice == "none"
        assert CHILD_REPORT_POLICY in messages[0]["content"]
        assert CHILD_REPORT_POLICY in messages[-1]["content"]
        assert "Choose the format and length appropriate to the task" in messages[-1]["content"]
        return {"content": text, "finish": finish, "reasoning": "verbatim final reasoning"}
    client = ScriptedClient(lambda messages, tools, choice: final(messages, choice))
    with Trace(tmp_path / "trace.jsonl", "limit") as trace:
        session = LeaderSubagent(client, trace, [SubagentTemplate("worker", "Work", "Worker", max_turns=1)])
        observation = session._delegate({"template": "worker", "task": "Report existing evidence."}, None)
        report = json.loads(observation.text)
        assert report["report"] == text and report["status"] == expected
        assert len(client.requests) == session.session_budget.snapshot()["model_calls"] == 1
        assert session.children["subagent-1"].messages[-1]["reasoning_content"] == "verbatim final reasoning"
        assert session.session_budget.snapshot()["tool_calls"] == 0
