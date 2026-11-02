import json

import pytest

from benchmarks.kramabench.adapter import KramaBenchSystem, make_session
from benchmarks.kramabench.offline import FixtureWorkspace, SingleFixtureClient, comparison_smoke
from benchmarks.kramabench.roles import ALL_TOOLS, LEADER_SYSTEM
from harness.single_agent import SingleAgent
from harness.trace import Trace, contexts, read_trace


def test_paired_smoke_independent_workspaces_and_equal_control(tmp_path, monkeypatch):
    import httpx
    def forbid(*args, **kwargs):
        raise AssertionError("No paid or network calls in comparison smoke")
    monkeypatch.setattr(httpx.Client, "send", forbid)
    output = tmp_path / "pair"
    summary = comparison_smoke(output)
    assert summary["status"] == "completed"
    assert summary["evaluation"] == "not_run" and summary["fixture_only"]
    assert set(summary["arms"]) == {"single", "team"}
    for mode, arm in summary["arms"].items():
        assert arm["response"]["explanation"]["answer"] == 4
        assert arm["status"] == "done" and not arm["infra_affected"]
        assert arm["cost_usd_actual"] == 0 and arm["integrity_errors"] == []
        assert arm["budget"]["model_limit"] == 40
        assert arm["budget"]["tool_limit"] == 80
        events = read_trace(output / mode / "attempt/trace.jsonl")
        audits = [e for e in events if e["type"] == "session_workspace_snapshot"]
        assert audits[0]["snapshot"]["files"] == {}
        assert set(audits[-1]["snapshot"]["files"]) == {"answer.json", "pipeline.py"}
    assert summary["arms"]["single"]["usage"]["total"]["llm_calls"] == 4
    assert summary["arms"]["team"]["usage"]["total"]["llm_calls"] >= 5
    manifest = json.loads((output / "single/attempt/manifest.json").read_text())
    assert manifest["active_templates"] == []
    assert manifest["limits"]["max_workers"] == 0
    assert manifest["context_mode"] == "full_task_and_own_history"
    assert set(manifest["domain_tools"]) == set(ALL_TOOLS)
    assert "Subagents:" not in manifest["leader_system"]
    for mode in ("single", "team"):
        model_manifest = json.loads((output / mode / "attempt/manifest.json").read_text())
        assert model_manifest["leader_system"].startswith(LEADER_SYSTEM)
    single_history = contexts(read_trace(output / "single/attempt/trace.jsonl"))
    assert set(single_history) == {"leader"}
    assert len([m for m in single_history["leader"] if m["role"] == "tool"]) == 4
    assert (output / "single/fixture/work").resolve() != (output / "team/fixture/work").resolve()
    (output / "single/fixture/work/answer.json").write_text("single-only mutation")
    assert json.loads((output / "team/fixture/work/answer.json").read_text())["answer"] == 4
    with pytest.raises(FileExistsError):
        comparison_smoke(output)


def test_native_api_accepts_explicit_single_mode(tmp_path):
    workspace = FixtureWorkspace(tmp_path / "fixture")
    system = KramaBenchSystem(client=SingleFixtureClient(), mode="single", domain="archeology",
        output=tmp_path / "outputs", workspace_factory=lambda *args: workspace)
    assert system.name == "single_agent"
    system.process_dataset(workspace.data)
    result = system.serve_query("Return average. LEADER_ONLY_SENTINEL", "single-task", [])
    assert result["explanation"]["answer"] == 4


def test_legacy_flag_is_rejected(tmp_path):
    fixture = FixtureWorkspace(tmp_path / "fixture")
    with Trace(tmp_path / "trace.jsonl", "legacy") as trace:
        with pytest.raises(ValueError, match="retired"):
            make_session(SingleFixtureClient(), trace, fixture, delegated=False)
