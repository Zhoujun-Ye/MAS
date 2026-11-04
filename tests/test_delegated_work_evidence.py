import json
import threading
from types import SimpleNamespace

import pytest

from analysis.native_evidence import native_subagents, read_evidence
from benchmarks.kramabench.tasks import Task
from scripts.kramabench import cli_runtime


def write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows))


def claude_lifecycle(folder, workers):
    events = [dict(hook_event_name="SessionStart", session_id="root")]
    for worker in workers:
        events.extend([dict(hook_event_name="SubagentStart", agent_id=worker),
                       dict(hook_event_name="SubagentStop", agent_id=worker)])
    events.append(dict(hook_event_name="SessionEnd", session_id="root"))
    write_rows(folder / "native-profile/observer/events.jsonl", events)


def test_claude_reports_child_requests_without_claiming_substance(tmp_path):
    claude_lifecycle(tmp_path, ["compute", "reason"])
    child_dir = tmp_path / "native-profile/claude/projects/fixture/subagents"
    tool = dict(type="tool_use", id="call-1", name="Bash", input={})
    message = dict(message=dict(id="message-1", role="assistant", content=[tool]))
    write_rows(child_dir / "agent-compute.jsonl", [message, message])
    write_rows(child_dir / "agent-reason.jsonl", [dict(message=dict(id="message-2", role="assistant",
        content=[dict(type="text", text="A reasoning-only contribution")]))])
    audit = native_subagents(tmp_path)
    assert audit["passed"] and audit["structural_delegation_complete"]
    assert audit["substantive_work_status"] == "unverified"
    children = {row["agent_id"]: row for row in audit["child_tool_evidence"]}
    assert children["compute"]["tool_counts"] == {"Bash": 1}
    assert children["compute"]["tool_calls_observed"] == 1
    assert children["reason"]["tool_calls_observed"] == 0
    assert children["reason"]["substantive_work_status"] == "unverified"
    accounting = read_evidence(tmp_path / "native-profile", "claude-code")
    assert accounting["substantive_work_status"] == "unverified"
    assert accounting["child_tool_evidence"] == audit["child_tool_evidence"]


def test_missing_child_transcripts_do_not_become_zero_tool_claims(tmp_path):
    claude_lifecycle(tmp_path, ["worker"])
    audit = native_subagents(tmp_path)
    assert audit["passed"]
    assert audit["child_tool_evidence_status"] == "unavailable"
    assert audit["child_tool_evidence"] == []
    assert audit["substantive_work_status"] == "unverified"


@pytest.mark.parametrize("backend", ["claude-code-subagents"])
def test_lead_organization_is_not_written_to_worker_workspace_rules(tmp_path, monkeypatch, backend):
    captured = {}
    lead_prompt = "Lead-only organization instructions"
    class Gateway:
        url = "http://127.0.0.1:8765"
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
    class Adapter:
        def __init__(self, *args):
            pass
        def run(self, prompt, **kwargs):
            captured["prompt"] = prompt
            for name in ("AGENTS.md", "CLAUDE.md"):
                assert (kwargs["workspace"] / name).read_text() == cli_runtime.INSTRUCTIONS
            return dict(status="cli_exited")
    monkeypatch.setattr(cli_runtime, "condition_instructions", lambda *a: lead_prompt)
    monkeypatch.setattr(cli_runtime, "CredentialGateway", Gateway)
    monkeypatch.setattr(cli_runtime, "ClaudeCodeSubagentsCLI", Adapter)
    monkeypatch.setattr(cli_runtime, "container", lambda *a, **kw: "fixture-container")
    monkeypatch.setattr(cli_runtime, "stop_container", lambda *a: dict(stopped=True))
    monkeypatch.setattr(cli_runtime, "native_subagents", lambda *a: dict(passed=True, native_team_configs=0, teammate_idle_events=0))
    monkeypatch.setattr(cli_runtime.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0))
    args = SimpleNamespace(output=tmp_path / "out", upstream=tmp_path, image="fixture", timeout=900)
    result = cli_runtime.run_attempt(Task("probe", "astronomy", "Fixture"), backend, args,
        "synthetic-secret", threading.Event(), set(), threading.Lock())
    assert result["status"] == "cli_exited"
    assert captured["prompt"].endswith(lead_prompt)
