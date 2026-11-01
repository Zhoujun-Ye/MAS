import json
import threading

import pytest

from benchmarks.kramabench.adapter import make_session
from benchmarks.kramabench.offline import FixtureWorkspace
from benchmarks.kramabench.roles import (
    ALL_TOOLS, CATALOG_VERSION, DELEGATION_GUIDANCE, DELIVERABLE_CONTRACT,
    FINDINGS_CONTRACT, READ_TOOLS, TEMPLATES,
)
from fakes import ScriptedClient
from harness.agent import Observation
from harness.subagents import CHILD_REPORT_POLICY
from harness.trace import Trace, read_trace, validate


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda template: template.name)
def test_every_role_has_fixed_grants_and_identity_free_prefix(tmp_path, template):
    client = ScriptedClient(lambda *args: {"content": "Not checked: scripted role inspection."})
    workspace = FixtureWorkspace(tmp_path / "fixture")
    with Trace(tmp_path / "trace.jsonl", "roles") as trace:
        session, catalog = make_session(client, trace, workspace)
        for task in ("LOCAL_BRIEF_SENTINEL_A", "LOCAL_BRIEF_SENTINEL_B"):
            report = session._delegate({"template": template.name, "task": task}, None)
            assert json.loads(report.text)["status"] == "completed"
        first, second = session.children.values()
        assert first.messages[0] == second.messages[0]
        assert CHILD_REPORT_POLICY in first.messages[0]["content"]
        assert first.schemas == second.schemas
        assert set(first.tools) == set(template.tools)
        assert "LOCAL_BRIEF_SENTINEL" not in first.messages[0]["content"]
        if template.name in {"data_scout", "requirement_analyst", "pipeline_analyst",
                             "data_preparer", "calculation_worker"}:
            assert DELIVERABLE_CONTRACT in first.messages[0]["content"]
            assert FINDINGS_CONTRACT not in first.messages[0]["content"]
        else:
            assert FINDINGS_CONTRACT in first.messages[0]["content"]
        for name in set(ALL_TOOLS) | {"delegate"}:
            if name not in template.tools:
                obs = first.run_tool({"id": "denied-" + name, "function": {"name": name, "arguments": "{}"}})
                assert obs.meta["error"]
        if template.tools == READ_TOOLS:
            assert all(tool.read_only for tool in first.tools.values())
        else:
            assert template.tools == ALL_TOOLS
            assert not first.tools["terminal"].read_only
            assert "not a runtime-enforced sandbox" in first.messages[0]["content"]
        assert len(catalog["templates"]) == 8
        assert CATALOG_VERSION == "kramabench-data-v9"


def test_mixed_review_roles_run_in_parallel_and_resume_the_right_scope(tmp_path):
    roles = ("data_auditor", "data_auditor", "reproduction_checker", "result_reviewer")
    scopes = ("source_quality", "join_cardinality", "numerical_method", "code_and_result")
    barrier = threading.Barrier(4)
    workspace = FixtureWorkspace(tmp_path / "fixture")
    pipeline = workspace.work / "pipeline.py"
    pipeline.write_text("# frozen fixture artifact\n")
    original_tools = workspace.tools

    def toolset():
        tools = original_tools()
        for tool in tools:
            if tool.name == "terminal":
                def check(args, agent):
                    # Fixed trusted fixture operation, not arbitrary host execution.
                    name = args["command"]
                    assert name in scopes[:3]
                    directory = workspace.work / "checks" / name
                    directory.mkdir(parents=True)
                    (directory / "evidence.json").write_text(json.dumps({"scope": name}))
                    return Observation("No issue found in fixture scope: " + name)
                tool.run = check
            elif tool.name == "read_file":
                def read(args, agent):
                    assert args["path"] == "/workspace/pipeline.py"
                    return Observation(pipeline.read_text())
                tool.run = read
        return tools
    workspace.tools = toolset

    def policy(messages, tools, choice):
        if "delegate" in tools:
            reports = [json.loads(m["content"]) for m in messages if m["role"] == "tool"]
            if not reports:
                return {"calls": [("delegate", {"template": name,
                    "task": f"Check only {scope}; read /workspace/pipeline.py; write only /workspace/checks/{scope}."
                    }) for name, scope in zip(roles, scopes)]}
            if len(reports) == 4:
                return {"calls": [("delegate", {"template": "data_auditor", "resume_id": "subagent-2",
                    "task": "Clarify the earlier join check; no new writes."})]}
            return {"calls": [("submit", {"answer": None, "pipeline_code": "",
                "evidence": "Checks integrated; no independent benchmark verdict.", "unfinished": []})]}
        assert "LEADER_ONLY_SENTINEL" not in json.dumps(messages)
        role = next(t.name for t in TEMPLATES if messages[0]["content"].startswith(t.system))
        assert role in roles
        if messages[-1]["role"] == "user":
            if any(m["role"] == "assistant" for m in messages):
                assert role == "data_auditor"
                assert "join_cardinality" in json.dumps(messages)
                assert "source_quality" not in json.dumps(messages)
                assert any(m["role"] == "tool" for m in messages)
                return {"content": "Follow-up: no issue found within the prior join scope; other checks not performed."}
            barrier.wait(timeout=10)
            if role == "result_reviewer":
                return {"calls": [("read_file", {"path": "/workspace/pipeline.py"})]}
            scope = next(scope for scope in scopes[:3] if scope in messages[-1]["content"])
            return {"calls": [("terminal", {"command": scope})]}
        return {"content": messages[-1]["content"]}

    with Trace(tmp_path / "parallel.jsonl", "parallel-reviews") as trace:
        trace.emit("run_start")
        session, _ = make_session(ScriptedClient(policy), trace, workspace)
        outcome = session.run("Check pipeline; LEADER_ONLY_SENTINEL")
        assert outcome.status == "done" and not outcome.errors
        assert not outcome.infra_affected
        assert len(outcome.delegations) == 5
        assert len(session.children) == 4
        assert session.child_templates["subagent-2"] == "data_auditor"
        assert session.children["subagent-1"].messages[0] == session.children["subagent-2"].messages[0]
        assert session.children["subagent-2"].budget.used == 1
        assert outcome.budget["model_calls"] <= 40
        assert pipeline.read_text() == "# frozen fixture artifact\n"
        assert {p.parent.name for p in workspace.work.glob("checks/*/evidence.json")} == set(scopes[:3])
        trace.emit("final", text=outcome.text)
        trace.emit("run_end", status="completed")
    events = read_trace(tmp_path / "parallel.jsonl")
    assert validate(events) == []
    assert len([e for e in events if e["type"] == "workspace_snapshot"]) == 10


def test_delegation_guidance_is_not_added_to_solo_control(tmp_path):
    with Trace(tmp_path / "trace.jsonl", "control") as trace:
        workspace = FixtureWorkspace(tmp_path / "fixture")
        client = ScriptedClient(lambda *args: {"content": "done"})
        solo, _ = make_session(client, trace, workspace, delegated=False)
        team, _ = make_session(client, trace, workspace)
        assert DELEGATION_GUIDANCE in team.leader.messages[0]["content"]
        assert DELEGATION_GUIDANCE not in solo.leader.messages[0]["content"]
        assert solo.session_budget.snapshot() == team.session_budget.snapshot()


def test_merged_review_catalog_preserves_capabilities_and_rejects_retired_names(tmp_path):
    templates = {t.name: t for t in TEMPLATES}
    reviewers = {name for name, t in templates.items() if FINDINGS_CONTRACT in t.system}
    assert reviewers == {"data_auditor", "result_reviewer", "reproduction_checker"}
    assert templates["result_reviewer"].tools == READ_TOOLS
    assert "indexing" in templates["result_reviewer"].system
    assert "answer coverage" in templates["result_reviewer"].system
    assert "missing values" in templates["data_auditor"].system
    assert "many-to-many" in templates["data_auditor"].system
    assert "estimand" in templates["reproduction_checker"].system
    assert "same-method reproduction, not independent validation" in templates["reproduction_checker"].system
    assert all("not every capability" in templates[name].system for name in reviewers)
    client = ScriptedClient(lambda *args: pytest.fail("Retired names must not invoke a model"))
    with Trace(tmp_path / "retired.jsonl", "retired") as trace:
        session, _ = make_session(client, trace, FixtureWorkspace(tmp_path / "fixture"))
        before = session.session_budget.snapshot()
        for name in ("data_quality_auditor", "join_auditor", "statistical_auditor", "code_reviewer"):
            obs = session.leader.run_tool({"id": name, "function": {"name": "delegate",
                "arguments": json.dumps({"template": name, "task": "Check something"})}})
            assert obs.meta["error"]
        assert not session.children
        assert session.session_budget.snapshot() == before
