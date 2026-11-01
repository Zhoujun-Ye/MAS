from dataclasses import asdict
import json
from pathlib import Path

import pytest

from benchmarks.kramabench.adapter import KramaBenchSystem, make_session, parse_submission, run_task
from benchmarks.kramabench.offline import FixtureClient, FixtureWorkspace, PIPELINE, smoke
from benchmarks.kramabench.roles import ALL_TOOLS, READ_TOOLS, TEMPLATES
from benchmarks.kramabench.tasks import Task, public_tasks
from fakes import ScriptedClient
from harness.catalog import catalog_manifest
from harness.data_tools import inspection_tools
from harness.trace import Trace, contexts, read_trace, validate


def test_public_tasks_strip_all_reference_fields():
    task = public_tasks([{"id": "archeology-hard-1", "query": "Public question", "answer": "SECRET",
        "answer_type": "numeric_exact", "data_sources": ["oracle.csv"], "runtime": 1,
        "subtasks": [{"step": "SOLUTION", "answer": 7}]}], "archeology")[0]
    assert asdict(task) == {"id": "archeology-hard-1", "domain": "archeology", "query": "Public question"}
    with pytest.raises(ValueError):
        public_tasks([{"id": "a", "query": "q"}] * 2, "archeology")
    with pytest.raises(ValueError):
        Task("../escape", "archeology", "q")


def test_scripted_full_adapter(tmp_path, monkeypatch):
    import httpx
    def forbid(*args, **kwargs):
        raise AssertionError("No network/model/judge allowed")
    monkeypatch.setattr(httpx.Client, "send", forbid)
    response = smoke(tmp_path / "smoke")
    assert response == {"explanation": {"answer": 4.0}, "pipeline_code": PIPELINE}
    output = tmp_path / "smoke" / "attempt"
    events = read_trace(output / "trace.jsonl")
    assert validate(events) == []
    histories = contexts(events)
    assert histories["subagent-1"][0] == histories["subagent-2"][0]
    for name, history in histories.items():
        if name != "leader":
            assert "LEADER_ONLY_SENTINEL" not in json.dumps(history)
    ends = [e for e in events if e["type"] == "delegation_end"]
    assert len(ends) == 5 and all(e["status"] == "completed" for e in ends)
    assert ends[-1]["agent_id"] == ends[-2]["agent_id"]
    assert sum(e["type"] == "workspace_snapshot" for e in events) == 10
    report = json.loads((output / "report.json").read_text())
    assert report["evaluation"] == "not_run" and report["fixture_only"]
    assert report["usage"]["total"]["llm_calls"] == 15
    assert json.loads((output / "native_response.json").read_text())["model_output"] == {"answer": 4.0}
    with pytest.raises(FileExistsError):
        smoke(tmp_path / "smoke")


def test_fixed_grants_and_attempted_escalation(tmp_path):
    workspace = FixtureWorkspace(tmp_path / "fixture")
    client = ScriptedClient(lambda *args: {"content": "report"})
    with Trace(tmp_path / "trace.jsonl", "permissions") as trace:
        session, manifest = make_session(client, trace, workspace)
        session._delegate({"template": "data_scout", "task": "local only"}, None)
        scout = session.children["subagent-1"]
        assert set(scout.tools) == set(READ_TOOLS)
        assert all(tool.read_only for tool in scout.tools.values())
        for denied in ("terminal", "write_file", "delegate"):
            obs = scout.run_tool({"id": denied, "function": {"name": denied, "arguments": "{}"}})
            assert obs.meta["error"]
        assert set(session.leader.tools) == set(ALL_TOOLS) | {"delegate", "submit"}
        assert manifest["templates"][1]["tools"] == list(ALL_TOOLS)
        with pytest.raises(ValueError, match="fixed"):
            make_session(client, trace, workspace, leader_system="override")


def test_a0_a2_tools_and_prefix_stability(tmp_path):
    client = FixtureClient()
    workspaces = [FixtureWorkspace(tmp_path / str(i)) for i in range(2)]
    with Trace(tmp_path / "one.jsonl", "one") as trace1, Trace(tmp_path / "two.jsonl", "two") as trace2:
        first, catalog1 = make_session(client, trace1, workspaces[0])
        second, catalog2 = make_session(client, trace2, workspaces[1])
        assert first.leader.messages == second.leader.messages
        assert first.leader.schemas == second.leader.schemas
        assert catalog1 == catalog2
        solo, _ = make_session(client, trace2, workspaces[1], delegated=False)
        assert set(solo.leader.tools) == set(first.leader.tools) - {"delegate"}
        assert "Subagents:" not in solo.leader.messages[0]["content"]
        assert solo.session_budget.snapshot() == first.session_budget.snapshot()


@pytest.mark.parametrize("text", ["not JSON", "```json\n{}\n```", "[]", "{}",
    '{"answer": NaN,"pipeline_code":"","evidence":"","unfinished":[]}',
    '{"answer":1,"answer":2,"pipeline_code":"","evidence":"","unfinished":[]}',
    '{"answer":1,"pipeline_code":{},"evidence":"","unfinished":[]}'])
def test_malformed_submission_never_silently_becomes_score_zero(text):
    with pytest.raises(ValueError):
        parse_submission(text)


def test_failure_is_immutable_and_retained(tmp_path):
    client = ScriptedClient(lambda *args: {"content": "not json"})
    workspace = FixtureWorkspace(tmp_path / "fixture")
    output = tmp_path / "attempt"
    with pytest.raises(ValueError):
        run_task(Task("custom", "archeology", "question"), client=client, workspace=workspace,
                 output=output, dataset=workspace.data)
    assert (output / "outcome.json").exists()
    assert (output / "failure.json").exists()
    assert not (output / "native_response.json").exists()
    assert validate(read_trace(output / "trace.jsonl")) == []
    with pytest.raises(FileExistsError):
        run_task(Task("custom", "archeology", "q"), client=client, workspace=workspace,
                 output=output, dataset=workspace.data)


def test_system_api_rejects_oracle_subset_before_factory(tmp_path):
    calls = []
    system = KramaBenchSystem(client=FixtureClient(), workspace_factory=lambda *args: calls.append(args),
                             output=tmp_path / "out", domain="archeology")
    with pytest.raises(ValueError, match="process_dataset"):
        system.serve_query("question", "task", [])
    system.process_dataset(tmp_path)
    with pytest.raises(ValueError, match="Oracle"):
        system.serve_query("question", "task", ["gold_file.csv"])
    assert not calls


def test_system_api_output_shape(tmp_path):
    workspace = FixtureWorkspace(tmp_path / "workspace")
    system = KramaBenchSystem(client=FixtureClient(),
        workspace_factory=lambda dataset, output: workspace,
        output=tmp_path / "out", domain="archeology")
    system.process_dataset(workspace.data)
    assert system.serve_query("average", "custom", [])["explanation"]["answer"] == 4
    with pytest.raises(FileExistsError):
        system.serve_query("average", "custom", [])


def test_inspection_pagination_and_escape(tmp_path):
    workspace = FixtureWorkspace(tmp_path / "fixture")
    tools = {t.name: t for t in inspection_tools(workspace)}
    obs = tools["list_files"].run({"area": "data", "limit": 1}, None)
    assert json.loads(obs.text)["entries"][0]["path"] == "values.csv"
    obs = tools["inspect_file"].run({"area": "data", "path": "values.csv", "limit": 5}, None)
    assert json.loads(obs.text)["next_offset"] == 5
    (workspace.data / "escape").symlink_to(tmp_path)
    for path in ("../work", "escape", str(tmp_path)):
        assert tools["inspect_file"].run({"area": "data", "path": path}, None).meta["error"]
    # Shell-like names are literal paths, not commands.
    malicious = "$(touch HACKED).csv"
    (workspace.data / malicious).write_text("literal")
    assert "literal" in tools["inspect_file"].run({"area": "data", "path": malicious}, None).text
    assert not (workspace.root / "HACKED").exists()


def test_catalog_is_detached_and_unknown_permissions_rejected(tmp_path):
    workspace = FixtureWorkspace(tmp_path / "fixture")
    tools = workspace.tools() + inspection_tools(workspace)
    frozen = catalog_manifest(TEMPLATES, tools)
    tools[0].parameters["properties"]["injected"] = {"type": "string"}
    assert "injected" not in json.dumps(frozen)
    with pytest.raises(ValueError):
        catalog_manifest(TEMPLATES, [])


def test_pinned_workload_validation(tmp_path, monkeypatch):
    from benchmarks.kramabench.tasks import DOMAINS, UPSTREAM_COMMIT, load_tasks
    (tmp_path / "workload").mkdir()
    blobs = {}
    for domain in DOMAINS:
        relative = f"workload/{domain}.json"
        blobs[relative] = json.dumps([{"id": domain + "-task", "query": "question", "answer": "secret"}]).encode()
        (tmp_path / relative).write_bytes(blobs[relative])
    head = [UPSTREAM_COMMIT]
    def git(command):
        if command[-2:] == ["rev-parse", "HEAD"]:
            return head[0].encode()
        return blobs[command[-1].split(":", 1)[1]]
    monkeypatch.setattr("benchmarks.kramabench.tasks.subprocess.check_output", git)
    tasks, provenance = load_tasks(tmp_path)
    assert len(tasks) == 6 and len(provenance["workload_sha256"]) == 6
    head[0] = "different-revision"
    with pytest.raises(ValueError, match="revision"):
        load_tasks(tmp_path)
    head[0] = UPSTREAM_COMMIT
    (tmp_path / "workload/archeology.json").write_text("[]")
    with pytest.raises(ValueError, match="Modified workload"):
        load_tasks(tmp_path)
