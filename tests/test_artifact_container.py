"""Opt-in transport smoke using an existing image; no pull, install or model."""

import hashlib
import json
import os
import subprocess
import uuid

import pytest

from harness.execution import ContainerWorkspace
from harness.trace import Trace, contexts, read_trace, validate
from benchmarks.kramabench.adapter import make_session, parse_submission
from fakes import ScriptedClient
from test_team import call, inbox, invoke, names_used


@pytest.fixture
def container_workspace(tmp_path):
    if not os.environ.get("MAS_ARTIFACT_TEST_IMAGE"):
        pytest.skip("Explicit existing-image opt-in required")
    image = os.environ["MAS_ARTIFACT_TEST_IMAGE"]
    subprocess.run(["docker", "image", "inspect", image], capture_output=True, check=True)
    work = tmp_path / "work"
    work.mkdir()
    subprocess.run(["git", "-C", str(work), "init", "-q"], check=True)
    name = "mas-artifact-test-" + uuid.uuid4().hex
    subprocess.run(["docker", "run", "--detach", "--rm", "--pull", "never", "--name", name,
        "--label", "mas-information.test=artifact-export", "--network", "none", "--cpus", "1",
        "--memory", "256m", "--pids-limit", "64", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--read-only", "--tmpfs", "/tmp", "--user", f"{os.getuid()}:{os.getgid()}", "--workdir", "/workspace",
        "--mount", f"type=bind,src={work},dst=/workspace", image, "sleep", "120"], capture_output=True, check=True)
    try:
        yield ContainerWorkspace(name, archive_dir=tmp_path / "retained"), work
    finally:
        subprocess.run(["docker", "rm", "--force", name], capture_output=True, check=True)


def test_snapshot_bound_artifact_export_in_real_container(container_workspace):
    workspace, work = container_workspace
    data = ("# synthetic export fixture\r\n" * 2000 + "print('\\u4e2d')\n").encode()
    artifact = work / "pipeline.py"
    artifact.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    snapshot = workspace.audit_snapshot()
    assert snapshot["files"]["pipeline.py"] == {"kind": "file", "sha256": digest}
    exported = workspace.export_artifact("/workspace/pipeline.py", digest)
    assert exported["content"].encode() == data
    assert exported["sha256"] == digest and exported["bytes"] == len(data)
    for path, target in (("link.py", artifact), ("linked-dir", work)):
        (work / path).symlink_to(target.name if path == "link.py" else ".")
    for path in ("link.py", "linked-dir/pipeline.py"):
        with pytest.raises(ValueError):
            workspace.export_artifact(path, digest)
    os.mkfifo(work / "pipe")
    with pytest.raises(ValueError):
        workspace.export_artifact("pipe", digest)
    artifact.write_bytes(b"print('changed after snapshot')\n")
    with pytest.raises(ValueError):
        workspace.export_artifact("pipeline.py", digest)


@pytest.mark.parametrize("mode", ["single", "team"])
def test_many_intermediates_export_only_selected_pipeline_in_container(container_workspace, tmp_path, monkeypatch, mode):
    workspace, work = container_workspace
    intermediates = work / "a_outputs"
    intermediates.mkdir()
    for i in range(130):
        (intermediates / f"part-{i:03d}.csv").write_text("value\n1\n")
    (intermediates / "binary.bin").write_bytes(b"\x00\xff")
    pipeline = work / "worker" / "pipeline.py"
    pipeline.parent.mkdir()
    pipeline.write_text("print(4)\n")
    exports = []
    export = workspace.export_artifact
    def read(path, *args, **kwargs):
        exports.append(path)
        return export(path, *args, **kwargs)
    monkeypatch.setattr(workspace, "export_artifact", read)
    with Trace(tmp_path / "trace.jsonl", "many-container-files") as trace:
        session, _ = make_session(ScriptedClient(lambda *a: {}), trace, workspace, mode=mode)
        if mode == "team":
            with session.condition:
                session._freeze()
            assert not exports
        receipt = invoke(session.leader, "submit", answer=4, pipeline_path="worker/pipeline.py", evidence="transport fixture", unfinished=[])
        assert not receipt.meta.get("error")
        assert len(session.frozen_files) == 132 and exports == ["worker/pipeline.py"]
        assert parse_submission(session.leader.submission)["pipeline_code"] == "print(4)\n"
        assert not session.infra_affected and session.session_budget.snapshot()["tool_calls"] == 0


@pytest.mark.parametrize("leader_mode", ["coordinator", "full"])
def test_coordinator_delegates_production_and_execution_check_before_freeze(container_workspace, tmp_path, leader_mode):
    workspace, work = container_workspace
    code = "print(2 + 2)\n"
    checked = []
    def policy(messages, tools, choice):
        used = names_used(messages)
        if messages[0]["content"].startswith("Solve the data-analysis"):
            assert bool(set(tools) & {"terminal", "read_file", "inspect_file", "write_file", "list_files", "read_output"}) == (leader_mode == "full")
            if not used:
                return call("spawn_worker", template="worker", task="produce", write_scope="producer")
            if len(team.reports) == 1 and len(team.members) == 1:
                return call("spawn_worker", template="verifier", task="Run /workspace/producer/pipeline.py and check output 4",
                            depends_on=["task-1"], write_scope="checks")
            if len(team.reports) < 2:
                return call("wait_event")
            if "finish_team" not in used:
                assert checked == [True]
                return call("finish_team", reason="Worker execution check returned")
            closing = next(json.loads(r["content"]) for r in inbox(messages)
                           if '"event": "team_closed"' in r["content"])
            files = closing["state"]["frozen_files"]
            path = next(p for p, r in files.items() if r["submission_status"] == "hash_recorded")
            assert path == "producer/pipeline.py"
            assert code.strip() not in json.dumps(messages)
            return call("submit", answer=4, pipeline_path=path, evidence="Worker ran the saved file and observed 4", unfinished=[])
        task = json.loads(messages[1]["content"])["task"]
        if task == "produce" and not used:
            return call("write_file", path="/workspace/producer/pipeline.py", content=code)
        if "terminal" not in used:
            return call("terminal", command="python3 /workspace/producer/pipeline.py")
        last = next(m["content"] for m in reversed(messages) if m["role"] == "tool")
        assert "Exit code: 0" in last and last.rstrip().endswith("4")
        if task != "produce":
            checked.append(True)
        return call("finish_task", status="completed", summary="producer/pipeline.py executed; observed output 4")
    with Trace(tmp_path / "trace.jsonl", "worker-verification") as trace:
        trace.emit("run_start")
        team, _ = make_session(ScriptedClient(policy), trace, workspace, session_seconds=30, leader_mode=leader_mode)
        outcome = team.run("Produce a Python pipeline returning 4 and have another Worker run it to check the output.")
        trace.emit("final", text=outcome.text)
        trace.emit("run_end", status="completed")
    assert outcome.status == "done" and not outcome.errors and not outcome.infra_affected
    assert parse_submission(outcome.text)["pipeline_code"] == code
    assert checked == [True] and len(team.members) == 2
    events = read_trace(trace.path)
    assert validate(events) == []
    assert code.strip() not in json.dumps(contexts(events)["leader"])
    executions = [e for e in events if e["type"] == "tool_call" and e["tool"] == "terminal"]
    assert [e["agent"] for e in executions] == ["worker-1", "worker-2"]
    assert executions[-1]["t"] < next(e["t"] for e in events if e["type"] == "team_frozen")
