"""Scripted production workflow, not proof of real-model routing or speed."""

import csv
import json
import threading
from collections import Counter

import pytest

from benchmarks.kramabench.adapter import make_session, parse_submission
from benchmarks.kramabench.offline import FixtureWorkspace, PIPELINE
from benchmarks.kramabench.roles import TEMPLATES
from harness.agent import Observation
from harness.trace import Trace, read_trace, validate
from tests.fakes import ScriptedClient


@pytest.mark.parametrize("mode", ["single", "mas"])
def test_small_task_can_finish_directly_without_forced_delegation_or_review(tmp_path, mode):
    workspace = FixtureWorkspace(tmp_path / "fixture")
    def policy(messages, tools, choice):
        assert "ROOT_ONLY_SENTINEL" in messages[1]["content"]
        results = [m for m in messages if m["role"] == "tool"]
        if not results:
            return {"calls": [("terminal", {"command": "fixture_average"})]}
        return {"calls": [("submit", {"answer": json.loads(results[-1]["content"])["answer"],
            "pipeline_code": PIPELINE, "evidence": "Direct fixed-fixture calculation.", "unfinished": []})]}
    with Trace(tmp_path / "direct.jsonl", mode) as trace:
        session, _ = make_session(ScriptedClient(policy), trace, workspace, mode=mode)
        outcome = session.run("Mean of values.csv. ROOT_ONLY_SENTINEL")
        assert outcome.status == "done" and not outcome.errors and not outcome.infra_affected
        assert parse_submission(outcome.text)["answer"] == 4
        assert outcome.budget["model_calls"] == 2 and outcome.budget["tool_calls"] == 1
        assert not session.children and not outcome.delegations


def test_early_parallel_producers_then_dependent_pipeline_without_root_reimplementation(tmp_path, monkeypatch):
    import httpx
    def no_network(*args, **kwargs):
        raise AssertionError("No network in scripted production regression")
    monkeypatch.setattr(httpx.Client, "send", no_network)
    workspace = FixtureWorkspace(tmp_path / "fixture")
    (workspace.data / "other.csv").write_text("value\n1\n3\n5\n")
    barrier = threading.Barrier(2)
    actions = Counter()
    original_tools = workspace.tools
    pipeline = (
        "import csv, json\n"
        "def mean(path):\n"
        "    with open(path) as f:\n"
        "        values = [float(r['value']) for r in csv.DictReader(f)]\n"
        "    return sum(values) / len(values)\n"
        "print(json.dumps({'values_mean': mean('/data/values.csv'), "
        "'other_mean': mean('/data/other.csv')}))\n"
    )

    def toolset():
        tools = original_tools()
        def execute(args, agent):
            operation = args["command"]
            assert (agent.name, operation) in {
                ("subagent-1", "prepare_values"), ("subagent-2", "calculate_other"),
                ("subagent-3", "integrate_ready_artifacts"),
            }
            actions[(agent.name, operation)] += 1
            if operation in {"prepare_values", "calculate_other"}:
                # Both actual tool operations must be active before either can finish.
                barrier.wait(timeout=10)
                source = "values.csv" if operation == "prepare_values" else "other.csv"
                with (workspace.data / source).open() as stream:
                    values = [float(row["value"]) for row in csv.DictReader(stream)]
                directory = "prepared" if operation == "prepare_values" else "other"
                payload = {"values": values} if directory == "prepared" else {"mean": sum(values) / len(values)}
            else:
                prepared = json.loads((workspace.work / "prepared/result.json").read_text())
                other = json.loads((workspace.work / "other/result.json").read_text())
                directory = "integrated"
                payload = {"values_mean": sum(prepared["values"]) / len(prepared["values"]),
                           "other_mean": other["mean"]}
            output = workspace.work / directory
            output.mkdir()
            (output / "result.json").write_text(json.dumps(payload))
            if directory == "integrated":
                (output / "pipeline.py").write_text(pipeline)
            return Observation(f"Saved /workspace/{directory}/result.json")
        def read(args, agent):
            assert agent.name == "leader"
            assert args["path"] in {"/workspace/integrated/pipeline.py", "/workspace/integrated/result.json"}
            actions[(agent.name, "read")] += 1
            return Observation((workspace.work / "integrated" / args["path"].rsplit("/", 1)[1]).read_text())
        for tool in tools:
            if tool.name == "terminal":
                tool.run = execute
            elif tool.name == "read_file":
                tool.run = read
        return tools
    workspace.tools = toolset
    root_turn = 0

    def policy(messages, tools, choice):
        nonlocal root_turn
        if "submit" in tools:
            root_turn += 1
            if root_turn == 1:
                assert not actions and not list(workspace.work.iterdir())
                return {"calls": [("delegate", {"template": "data_preparer",
                    "task": "Own parsing /data/values.csv into values; save /workspace/prepared/result.json with key values. Do not calculate the mean."}),
                    ("delegate", {"template": "calculation_worker",
                    "task": "Own sample mean of /data/other.csv; save /workspace/other/result.json with key mean. Do not inspect values.csv."})]}
            if root_turn == 2:
                assert (workspace.work / "prepared/result.json").exists()
                assert (workspace.work / "other/result.json").exists()
                return {"calls": [("delegate", {"template": "pipeline_analyst",
                    "task": "Compute values_mean from /workspace/prepared/result.json, combine other_mean from /workspace/other/result.json. Own /workspace/integrated. Save result.json and a self-contained pipeline.py reading the original CSVs. Do not recreate preparation or recompute other_mean.",
                    "context": "Ready artifacts: values is a numeric list; mean is sample mean. Raw sources are /data/values.csv and /data/other.csv."})]}
            if root_turn == 3:
                return {"calls": [("read_file", {"path": "/workspace/integrated/pipeline.py"}),
                                  ("read_file", {"path": "/workspace/integrated/result.json"})]}
            assert root_turn == 4
            return {"calls": [("submit", {"answer": json.loads(messages[-1]["content"]),
                "pipeline_code": messages[-2]["content"], "evidence": "Producer artifacts integrated; scripted checks only.",
                "unfinished": []})]}
        assert "ROOT_ONLY_SENTINEL" not in json.dumps(messages)
        assert "delegate" not in tools and "submit" not in tools
        role = next(t.name for t in TEMPLATES if messages[0]["content"].startswith(t.system))
        if messages[-1]["role"] == "user":
            return {"calls": [("terminal", {"command": {
                "data_preparer": "prepare_values", "calculation_worker": "calculate_other",
                "pipeline_analyst": "integrate_ready_artifacts",
            }[role]})]}
        return {"content": messages[-1]["content"]}

    with Trace(tmp_path / "production.jsonl", "production") as trace:
        trace.emit("run_start")
        session, _ = make_session(ScriptedClient(policy), trace, workspace)
        outcome = session.run("Return sample means of values.csv and other.csv. ROOT_ONLY_SENTINEL")
        submission = parse_submission(outcome.text)
        assert submission["answer"] == {"values_mean": 4, "other_mean": 3}
        assert submission["pipeline_code"] == pipeline
        assert outcome.status == "done" and not outcome.errors and not outcome.infra_affected
        assert session.child_templates == {"subagent-1": "data_preparer",
            "subagent-2": "calculation_worker", "subagent-3": "pipeline_analyst"}
        assert outcome.budget["model_calls"] == 10
        assert outcome.budget["tool_calls"] == 5
        trace.emit("final", text=outcome.text)
        trace.emit("run_end", status="completed")
    assert actions == {("subagent-1", "prepare_values"): 1, ("subagent-2", "calculate_other"): 1,
                       ("subagent-3", "integrate_ready_artifacts"): 1, ("leader", "read"): 2}
    events = read_trace(tmp_path / "production.jsonl")
    assert validate(events) == []
    calls = [e for e in events if e["type"] == "tool_call" and e["agent"] == "leader"]
    assert calls[0]["tool"] == "delegate"
    assert len([e for e in events if e["type"] == "workspace_snapshot"]) == 6
