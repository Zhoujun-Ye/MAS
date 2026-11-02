"""Scripted scheduling, selected-artifact export and specialist-team regressions."""

import json
import time

import pytest

from benchmarks.kramabench.adapter import make_session
from benchmarks.kramabench.offline import FixtureWorkspace, PIPELINE
from benchmarks.kramabench.roles import ALL_TOOLS, PROJECT_CONTEXT, SUBMISSION_INSTRUCTIONS, TEMPLATES
from fakes import ScriptedClient
from harness.agent import Observation, Tool
from harness.trace import Trace, activation_summary, communication_summary, read_trace, validate
from test_team import call, inbox, invoke, make, names_used


@pytest.mark.parametrize("blocked", [False, True])
def test_repeated_indefinite_wait_drains_and_preserves_submit(tmp_path, blocked):
    def policy(messages, tools, choice):
        if messages[0]["content"].startswith("Solve the data-analysis"):
            if team.phase == "frozen":
                return call("submit", answer=None, pipeline_path=None, evidence="Stopped without progress",
                            unfinished=["Prerequisite unavailable"])
            if blocked and not names_used(messages):
                return call("spawn_worker", template="worker", task="Blocked fixture")
            return call("wait_event")
        if choice == "none":
            return {"content": "Prerequisite still missing; unfinished"}
        return call("report_status", status="blocked", summary="No prerequisite")
    with Trace(tmp_path / "trace.jsonl", "stall") as trace:
        trace.emit("run_start")
        team, _ = make_session(ScriptedClient(policy), trace, FixtureWorkspace(tmp_path / "fixture"), session_seconds=3)
        started = time.monotonic()
        result = team.run("root")
        elapsed = time.monotonic() - started
        trace.emit("final", text=result.text)
        trace.emit("run_end", status="completed")
    assert elapsed < 2
    assert result.status == "done" and team.phase == "frozen"
    assert team.close_reason == "no_runnable_work" and team.leader.submission is not None
    assert result.budget["model_calls"] < 10
    assert not result.infra_affected
    if blocked:
        assert result.reports[0]["outcome"] == "partial"
    assert validate(read_trace(trace.path)) == []


def test_finitely_waiting_member_is_not_a_deadlock(tmp_path):
    def policy(messages, tools, choice):
        if messages[0]["content"].startswith("Coordinate"):
            if not names_used(messages):
                return call("spawn_worker", template="worker", task="Wait for a timer")
            if team.phase == "frozen":
                return {"content": "done"}
            if team.reports:
                return call("finish_team", reason="Timer worker returned")
            return call("wait_event")
        if not names_used(messages):
            return call("wait_event", timeout_seconds=0.05)
        return {"content": "timer completed"}
    with Trace(tmp_path / "trace.jsonl", "timer") as trace:
        team = make(trace, policy)
        result = team.run("root")
    assert result.status == "done" and team.close_reason == "Timer worker returned"
    events = read_trace(trace.path)
    assert not any(e["type"] == "team_message" and '"event": "no_runnable_work"' in e["content"] for e in events)
    assert not any(e["type"] == "team_stall_resolution" for e in events)


def test_stall_detector_accounts_for_queued_work_and_deliverable_mail(tmp_path):
    with Trace(tmp_path / "trace.jsonl", "progress-source") as trace:
        team = make(trace, lambda *a: {})
        invoke(team.leader, "spawn_worker", template="worker", task="ready")
        assert not team._no_progress_source()
        member = team.members["worker-1"]
        member.active, member.state, member.wait_until = True, "waiting", time.monotonic() + 1
        assert not team._no_progress_source()
        member.wait_until = None
        assert team._no_progress_source()
        invoke(team.leader, "send_message", to="worker-1", content="wake")
        assert not team._no_progress_source()


@pytest.mark.parametrize("mode", ["single", "team"])
def test_130_csvs_and_binary_files_do_not_starve_pipeline_export(tmp_path, monkeypatch, mode):
    with Trace(tmp_path / "trace.jsonl", "many-files") as trace:
        workspace = FixtureWorkspace(tmp_path / "fixture")
        output = workspace.work / "a_outputs"
        output.mkdir()
        for i in range(130):
            (output / f"part-{i:03d}.csv").write_text("value\n1\n")
        for i in range(3):
            (output / f"binary-{i}.bin").write_bytes(b"\x00\xff")
        pipeline = workspace.work / "worker" / "pipeline.py"
        pipeline.parent.mkdir()
        pipeline.write_text(PIPELINE)
        exports = []
        export = workspace.export_artifact
        def read(path, *args, **kwargs):
            exports.append(path)
            return export(path, *args, **kwargs)
        monkeypatch.setattr(workspace, "export_artifact", read)
        session, _ = make_session(ScriptedClient(lambda *a: {}), trace, workspace, mode=mode)
        if mode == "team":
            with session.condition:
                session._freeze()
            assert not exports
        receipt = invoke(session.leader, "submit", answer=4, pipeline_path="worker/pipeline.py", evidence="fixture", unfinished=[])
        assert not receipt.meta.get("error")
        assert len(session.frozen_files) == 134 and exports == ["worker/pipeline.py"]
        assert json.loads(session.leader.submission)["pipeline_code"] == PIPELINE
        assert session.session_budget.snapshot()["tool_calls"] == 0


def test_more_than_sixteen_message_wakes_still_allow_a_new_assignment(tmp_path):
    def policy(messages, tools, choice):
        used = names_used(messages)
        if messages[0]["content"].startswith("Coordinate"):
            if not used:
                return call("spawn_worker", template="worker", task="initial")
            if team.phase == "frozen":
                return {"content": "done"}
            if not team.reports:
                return call("wait_event")
            wakes = sum(r["cause"] == "message" for r in team.reports)
            if wakes < 17:
                if used.count("send_message") == wakes:
                    return call("send_message", to="worker-1", content=f"follow-up {wakes}")
                return call("wait_event")
            if "assign_task" not in used:
                return call("assign_task", worker_id="worker-1", task="new assignment")
            if len(team.reports) == 19:
                return call("finish_team", reason="all returned")
            return call("wait_event")
        return {"content": "returned"}
    with Trace(tmp_path / "trace.jsonl", "many-wakes") as trace:
        team = make(trace, policy, session_model_calls=64)
        result = team.run("root")
    assert result.status == "done" and not result.errors
    assert team.max_activations == 64 and team.activations == 19
    assert team.tasks["task-2"]["outcome"] == "done"
    usage = activation_summary(read_trace(trace.path))
    assert usage["by_cause"]["message"]["activations"] == 17
    assert all(r["task_id"] is None and r["previous_task_id"] == "task-1"
               for r in usage["activations"] if r["cause"] == "message")


def test_message_driven_domain_work_is_counted_separately(tmp_path):
    def policy(messages, tools, choice):
        used = names_used(messages)
        if messages[0]["content"].startswith("Coordinate"):
            if not used:
                return call("spawn_worker", template="worker", task="initial")
            if team.phase == "frozen":
                return {"content": "done"}
            if len(team.reports) == 1 and "send_message" not in used:
                return call("send_message", to="worker-1", content="perform follow-up")
            if len(team.reports) == 2:
                return call("finish_team", reason="follow-up complete")
            return call("wait_event")
        if inbox(messages) and "work" not in used:
            return call("work")
        return {"content": "done"}
    with Trace(tmp_path / "trace.jsonl", "message-work") as trace:
        team = make(trace, policy, [Tool("work", "work", {"type": "object"}, lambda *a: Observation("saved"), budgeted=True)])
        team.run("root")
    usage = activation_summary(read_trace(trace.path))
    assert usage["by_cause"]["assignment"]["domain_tool_calls"] == 0
    assert usage["by_cause"]["message"]["domain_tool_calls"] == 1
    assert len(team.tasks) == 1 and team.tasks["task-1"]["result_revision"] == 1
    message = next(r for r in usage["activations"] if r["cause"] == "message")
    assert message["trigger_message_ids"] and message["domain_tools"] == {"work": 1}


def test_specialist_policy_is_team_only_without_treatment_labels(tmp_path):
    with Trace(tmp_path / "trace.jsonl", "prompts") as trace:
        client = ScriptedClient(lambda *a: {})
        team, _ = make_session(client, trace, FixtureWorkspace(tmp_path / "team"), leader_mode="full")
        single, _ = make_session(client, trace, FixtureWorkspace(tmp_path / "single"), mode="single")
        assert {t.name for t in TEMPLATES} == {"worker", "explorer", "analyst", "verifier"}
        prompt = team.leader.messages[0]["content"]
        assert "meaningful multi-member decomposition" in prompt
        assert "single end-to-end owner" in prompt
        assert "meaningful multi-member decomposition" not in single.leader.messages[0]["content"]
        assert "ablation" not in prompt and "In Team mode" not in SUBMISSION_INSTRUCTIONS
        assert "weighting" not in PROJECT_CONTEXT and "interpolation" not in PROJECT_CONTEXT
        for template in TEMPLATES:
            assert set(template.tools) <= set(ALL_TOOLS)
            assert template.max_turns is None and template.tool_budget is None


def test_four_specialists_exchange_peer_information_and_release_dependencies(tmp_path):
    class Workspace(FixtureWorkspace):
        def calculate(self, args, agent):
            production = self.work / "production"
            if args == {"command": "fixture_verify"}:
                assert (production / "pipeline.py").read_text() == PIPELINE
                assert json.loads((production / "answer.json").read_text())["answer"] == 4
                return Observation("Fixture byte/output check passed; no arbitrary host code executed")
            observation = super().calculate(args, agent)
            production.mkdir()
            for path in ("pipeline.py", "answer.json"):
                (self.work / path).rename(production / path)
            return observation

    def policy(messages, tools, choice):
        used = names_used(messages)
        if messages[0]["content"].startswith("Solve the data-analysis"):
            if not used:
                return {"calls": [
                    ("spawn_worker", dict(template="explorer", task="sources", write_scope="sources")),
                    ("spawn_worker", dict(template="analyst", task="method", write_scope="analysis")),
                    ("spawn_worker", dict(template="worker", task="implement average", write_scope="production", depends_on=["task-1", "task-2"])),
                    ("spawn_worker", dict(template="verifier", task="verify production/pipeline.py", write_scope="checks", depends_on=["task-3"])),
                ]}
            if team.phase == "frozen":
                assert team.frozen_files["production/pipeline.py"]["submission_status"] == "hash_recorded"
                return call("submit", answer=4, pipeline_path="production/pipeline.py", evidence="Scripted specialist fixture", unfinished=[])
            if len(team.reports) == 4:
                return call("finish_team", reason="specialist handoffs returned")
            return call("wait_event")
        assert "ROOT_ONLY_SENTINEL" not in json.dumps(messages)
        task = json.loads(messages[1]["content"])["task"]
        mail = inbox(messages)
        if task == "sources":
            if "inspect_file" not in used:
                return call("inspect_file", area="data", path="values.csv")
            if "send_message" in used:
                return call("finish_task", status="completed", summary="values.csv schema shared with analyst")
            questions = [r for r in mail if r["needs_reply"]]
            if not questions:
                return call("wait_event")
            return call("send_message", to="worker-2", content="values.csv contains numeric value column",
                        reply_to=questions[0]["message_id"], kind="answer")
        if task == "method":
            if not used:
                return call("send_message", to="worker-1", content="Which numeric column?", needs_reply=True)
            if not any(r["kind"] == "answer" for r in mail):
                return call("wait_event")
            return call("finish_task", status="completed", summary="Compute arithmetic average of value in values.csv")
        if "terminal" not in used:
            return call("terminal", command="fixture_average" if task == "implement average" else "fixture_verify")
        return call("finish_task", status="completed", summary="production/pipeline.py; observed average 4; assigned fixture operation completed")

    with Trace(tmp_path / "trace.jsonl", "specialists") as trace:
        trace.emit("run_start")
        team, _ = make_session(ScriptedClient(policy), trace, Workspace(tmp_path / "fixture"), max_parallel=2)
        result = team.run("Find the average. ROOT_ONLY_SENTINEL")
        trace.emit("final", text=result.text)
        trace.emit("run_end", status="completed")
    assert result.status == "done" and not result.errors and not result.infra_affected
    assert [m.template for m in team.members.values()] == ["explorer", "analyst", "worker", "verifier"]
    events = read_trace(trace.path)
    assert validate(events) == [] and communication_summary(events)["peer_exposed"] == 2
    starts = {e["agent"]: e["t"] for e in events if e["type"] == "team_activation_start"}
    ends = {e["agent_id"]: e["t"] for e in events if e["type"] == "team_activation_end"}
    assert starts["worker-2"] < ends["worker-1"]
    assert starts["worker-3"] > max(ends["worker-1"], ends["worker-2"])
    assert starts["worker-4"] > ends["worker-3"]
