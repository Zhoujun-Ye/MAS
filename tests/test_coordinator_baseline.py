"""No paid calls: tool-level coordination and freeze-time submission contracts."""

import hashlib
import json

import pytest

from benchmarks.kramabench.adapter import make_session
from benchmarks.kramabench.offline import FixtureWorkspace, PIPELINE, comparison_smoke
from benchmarks.kramabench.roles import ALL_TOOLS, LEADER_SYSTEM, PROJECT_CONTEXT
from fakes import ScriptedClient
from harness.trace import Trace, contexts, read_trace
from test_team import invoke


CONTROLS = {"spawn_worker", "assign_task", "update_task", "continue_worker", "finish_team", "send_message",
            "read_messages", "resolve_request", "get_team_state", "wait_event", "submit"}


def test_default_leader_never_receives_domain_grants_even_read_only(tmp_path):
    with Trace(tmp_path / "trace.jsonl", "grants") as trace:
        workspace = FixtureWorkspace(tmp_path / "fixture")
        team, _ = make_session(ScriptedClient(lambda *a: {}), trace, workspace)
        assert team.leader_mode == "coordinator"
        assert set(team.leader.tools) == CONTROLS
        assert {s["function"]["name"] for s in team.leader.schemas} == CONTROLS
        for phase in ("open", "frozen"):
            team.phase = phase
            for name in ALL_TOOLS:
                assert invoke(team.leader, name).meta["error_kind"] == "permission_denied"
        assert not list(workspace.work.iterdir())
        assert team.session_budget.snapshot()["tool_calls"] == 0


def test_checklist_is_shared_by_single_and_all_workers_not_root_specific(tmp_path):
    with Trace(tmp_path / "trace.jsonl", "checklist") as trace:
        client = ScriptedClient(lambda *a: {})
        team, _ = make_session(client, trace, FixtureWorkspace(tmp_path / "team"))
        single, _ = make_session(client, trace, FixtureWorkspace(tmp_path / "single"), mode="single")
        for template in ("worker", "explorer"):
            invoke(team.leader, "spawn_worker", template=template, task="local work")
        actors = [single.leader, *(m.agent for m in team.members.values())]
        for actor in actors:
            assert PROJECT_CONTEXT in actor.messages[0]["content"]
            for item in ("output units and precision", "missing values", "join cardinality", "reproducibility"):
                assert item in actor.messages[0]["content"] and item not in LEADER_SYSTEM
            assert "endpoint mean" not in actor.messages[0]["content"]
        assert "assign a Worker to run the saved file" in team.leader.messages[0]["content"]
        assert set(ALL_TOOLS) <= single.leader.tools.keys()


@pytest.mark.parametrize("changed", [False, True])
def test_freeze_lists_hashes_and_submit_checks_only_selected_file(tmp_path, monkeypatch, changed):
    with Trace(tmp_path / "trace.jsonl", "freeze") as trace:
        workspace = FixtureWorkspace(tmp_path / "fixture")
        workspace.calculate({"command": "fixture_average"}, None)
        team, _ = make_session(ScriptedClient(lambda *a: {}), trace, workspace)
        reads = []
        export = workspace.export_artifact
        def capture(path, sha256, **kwargs):
            reads.append(path)
            return export(path, sha256, **kwargs)
        monkeypatch.setattr(workspace, "export_artifact", capture)
        with team.condition:
            team._freeze()
            team.mail.deliver(team.leader)
        assert reads == []
        record = team.frozen_files["pipeline.py"]
        assert record["sha256"] == hashlib.sha256(PIPELINE.encode()).hexdigest()
        assert record["submission_status"] == "hash_recorded"
        closing = json.dumps(team.leader.messages)
        assert "frozen_files" in closing and "pipeline.py" in closing
        assert PIPELINE not in closing and "import csv" not in closing
        if changed:
            (workspace.work / "pipeline.py").write_text("print('changed after freeze')\n")
        receipt = invoke(team.leader, "submit", answer=4, pipeline_path="/workspace/pipeline.py", evidence="fixture", unfinished=[])
        assert reads == ["pipeline.py"]
        if changed:
            assert receipt.meta["error_kind"] == "artifact_binding" and team.leader.submission is None
            return
        assert not receipt.meta.get("error")
        assert json.loads(team.leader.submission)["pipeline_code"] == PIPELINE
        assert "pipeline_code" not in json.loads(receipt.text)
        assert json.loads(receipt.text)["pipeline_path"] == "pipeline.py"


@pytest.mark.parametrize("mode", ["single", "team"])
def test_missing_file_or_missing_freeze_cannot_submit_code(tmp_path, mode):
    with Trace(tmp_path / "trace.jsonl", "missing") as trace:
        workspace = FixtureWorkspace(tmp_path / "fixture")
        session, _ = make_session(ScriptedClient(lambda *a: {}), trace, workspace, mode=mode)
        if mode == "team":
            with session.condition:
                session._freeze()
            workspace.calculate({"command": "fixture_average"}, None)
        obs = invoke(session.leader, "submit", answer=4, pipeline_path="pipeline.py", evidence="", unfinished=[])
        assert obs.meta["error_kind"] == "artifact_binding" and session.leader.submission is None


def test_freeze_lists_regular_files_and_rejects_symlinks_without_code(tmp_path, monkeypatch):
    with Trace(tmp_path / "trace.jsonl", "inventory") as trace:
        workspace = FixtureWorkspace(tmp_path / "fixture")
        (workspace.work / "a.py").write_text("print(1)\n")
        (workspace.work / "b.py").write_text("print(2)\n")
        (workspace.work / "link.py").symlink_to("a.py")
        snapshot = workspace.audit_snapshot()
        snapshot["files"]["link.py"]["kind"] = "symlink"
        monkeypatch.setattr(workspace, "audit_snapshot", lambda: snapshot)
        team, _ = make_session(ScriptedClient(lambda *a: {}), trace, workspace)
        with team.condition:
            team._freeze()
        assert team.frozen_files["a.py"]["submission_status"] == "hash_recorded"
        assert team.frozen_files["b.py"]["submission_status"] == "hash_recorded"
        assert team.frozen_files["link.py"]["submission_status"] == "not_regular"
        assert "print(1)" not in json.dumps(team.state())
        obs = invoke(team.leader, "submit", answer=2, pipeline_path="link.py", evidence="", unfinished=[])
        assert obs.meta["error_kind"] == "artifact_binding"
        assert not invoke(team.leader, "submit", answer=2, pipeline_path="b.py", evidence="", unfinished=[]).meta.get("error")


def test_single_invalid_retry_cannot_fall_back_to_previous_captured_bytes(tmp_path):
    with Trace(tmp_path / "trace.jsonl", "single-retry") as trace:
        workspace = FixtureWorkspace(tmp_path / "fixture")
        workspace.calculate({"command": "fixture_average"}, None)
        session, _ = make_session(ScriptedClient(lambda *a: {}), trace, workspace, mode="single")
        args = dict(answer=4, evidence="fixture", unfinished=[])
        assert invoke(session.leader, "submit", pipeline_path="missing.py", **args).meta["error"]
        (workspace.work / "pipeline.py").unlink()
        assert invoke(session.leader, "submit", pipeline_path="pipeline.py", **args).meta["error"]
        assert session.leader.submission is None


def test_unrelated_large_binary_does_not_prevent_selected_pipeline_export(tmp_path, monkeypatch):
    with Trace(tmp_path / "trace.jsonl", "byte-limit") as trace:
        workspace = FixtureWorkspace(tmp_path / "fixture")
        (workspace.work / "a.bin").write_bytes(b"\x00" * (17 * 1024 * 1024))
        (workspace.work / "b.py").write_text("print(2)\n")
        exports = []
        export = workspace.export_artifact
        def read(path, *args, **kwargs):
            exports.append(path)
            return export(path, *args, **kwargs)
        monkeypatch.setattr(workspace, "export_artifact", read)
        team, _ = make_session(ScriptedClient(lambda *a: {}), trace, workspace)
        with team.condition:
            team._freeze()
        assert not exports
        assert not invoke(team.leader, "submit", answer=2, pipeline_path="b.py", evidence="", unfinished=[]).meta.get("error")
        assert exports == ["b.py"]
        assert not team.infra_affected


def test_full_tool_ablation_cannot_read_domain_files_after_freeze(tmp_path):
    with Trace(tmp_path / "trace.jsonl", "ablation-closed") as trace:
        workspace = FixtureWorkspace(tmp_path / "fixture")
        workspace.calculate({"command": "fixture_average"}, None)
        team, _ = make_session(ScriptedClient(lambda *a: {}), trace, workspace, leader_mode="full")
        assert not invoke(team.leader, "read_file", path="/workspace/answer.json").meta.get("error")
        with team.condition:
            team._freeze()
        assert invoke(team.leader, "read_file", path="/workspace/answer.json").meta["error_kind"] == "team_admission_denied"


@pytest.mark.parametrize("mode", ["single", "team"])
def test_freeze_audit_only_time_is_accounted_equally(tmp_path, monkeypatch, mode):
    clock = [0.0]
    monkeypatch.setattr("harness.agent.time.monotonic", lambda: clock[0])
    with Trace(tmp_path / "trace.jsonl", "audit-clock") as trace:
        workspace = FixtureWorkspace(tmp_path / "fixture")
        digest = hashlib.sha256(PIPELINE.encode()).hexdigest()
        def snapshot(*, timeout=None):
            clock[0] += 2
            return {"files": {"pipeline.py": {"kind": "file", "sha256": digest}}}
        def export(path, sha256, *, timeout=None):
            clock[0] += 3
            return dict(path=path, sha256=sha256, content=PIPELINE, bytes=len(PIPELINE.encode()))
        monkeypatch.setattr(workspace, "audit_snapshot", snapshot)
        monkeypatch.setattr(workspace, "export_artifact", export)
        session, _ = make_session(ScriptedClient(lambda *a: {}), trace, workspace, mode=mode)
        session.session_budget.start()
        if mode == "team":
            with session.condition:
                session._freeze()
        response = invoke(session.leader, "submit", answer=4, pipeline_path="pipeline.py", evidence="fixture", unfinished=[])
        assert not response.meta.get("error")
        budget = session.session_budget.snapshot()
        assert budget["audit_wall_seconds"] == budget["audit_excluded_seconds"] == 5
        assert budget["execution_seconds"] == 0


def test_paired_fixture_exposes_no_pipeline_code_to_coordinator(tmp_path):
    output = tmp_path / "pair"
    comparison_smoke(output)
    for mode in ("single", "team"):
        attempt = output / mode / "attempt"
        manifest = json.loads((attempt / "manifest.json").read_text())
        assert manifest["leader_domain_tools"] == (sorted(ALL_TOOLS) if mode == "single" else [])
        assert manifest["team_arm"] == (None if mode == "single" else "coordinator_only")
        history = contexts(read_trace(attempt / "trace.jsonl"))["leader"]
        assert "import csv" not in json.dumps(history)
        assert "pipeline_code" not in json.loads(history[-1]["content"])
        assert json.loads((attempt / "submission.json").read_text())["pipeline_code"] == PIPELINE
