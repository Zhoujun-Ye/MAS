import copy
import json
from dataclasses import asdict

import pytest

from benchmarks.kramabench.adapter import run_task
from benchmarks.kramabench.offline import FixtureWorkspace
from benchmarks.kramabench.tasks import Task
from fakes import ScriptedClient
from harness.accounting import estimate
from harness.agent import Observation, SessionBudget, SessionLimit, Tool
from harness.comparison import validate_pair
from harness.container_contract import validate_artifact_paths
from harness.llm import ProviderError
from harness.catalog import CapabilityTemplate
from harness.session import comparison_session
from harness.trace import Trace, llm_inputs, read_trace, usage_summary

FINAL = json.dumps(dict(answer=4, pipeline_code="", evidence="fixture", unfinished=[]))


def test_artifact_paths_rejected_before_trace_or_model(tmp_path):
    workspace = FixtureWorkspace(tmp_path / "fixture")
    client = ScriptedClient(lambda *args: pytest.fail("No model calls before path rejection"))
    for root in (workspace.data, workspace.work):
        output = root / "unsafe"
        with pytest.raises(ValueError, match="overlap"):
            run_task(Task("task", "archeology", "secret"), client=client, workspace=workspace,
                     dataset=workspace.data, output=output)
        assert not output.exists()
    alias = tmp_path / "alias"
    alias.symlink_to(workspace.data, target_is_directory=True)
    with pytest.raises(ValueError, match="overlap"):
        validate_artifact_paths(workspace.data, alias / "output")
    workspace.archive_dir = workspace.data / "archive"
    with pytest.raises(ValueError, match="overlap"):
        run_task(Task("task", "archeology", "secret"), client=client, workspace=workspace,
                 dataset=workspace.data, output=tmp_path / "safe")
    assert not (tmp_path / "safe").exists() and not client.requests


@pytest.mark.parametrize("failure", ["json", "provider"])
def test_failure_always_has_a_report(tmp_path, failure):
    def policy(*args):
        if failure == "provider":
            raise ProviderError("http_500", "fixture", 500)
        return {"content": "not JSON"}
    workspace = FixtureWorkspace(tmp_path / "fixture")
    output = tmp_path / "attempt"
    with pytest.raises((ValueError, ProviderError)):
        run_task(Task("task", "archeology", "q"), client=ScriptedClient(policy), workspace=workspace,
                 dataset=workspace.data, output=output, mode="single", session_model_calls=1)
    report = json.loads((output / "report.json").read_text())
    assert report["status"] == "error" and report["failure"]
    assert report["submission_sha256"] is None and report["evaluation"] == "not_run"
    assert report["usage"]["total"]["attempted_calls"] == 1
    assert report["usage_complete"] == (failure == "json")
    assert not (output / "native_response.json").exists()




def test_audit_overlap_is_union_and_does_not_pause_running_execution(monkeypatch):
    now = [0.0]
    monkeypatch.setattr("harness.agent.time.monotonic", lambda: now[0])
    budget = SessionBudget(seconds=5, audit_seconds=20)
    budget.start()
    with budget.activity("audit"):
        now[0] = 1
        with budget.activity("audit"):
            with budget.activity("execution"):
                now[0] = 4
                assert budget.remaining_seconds() == 2
            now[0] = 6
        now[0] = 7
    assert budget.snapshot()["audit_excluded_seconds"] == 4
    assert budget.snapshot()["audit_wall_seconds"] == 7
    now[0] = 9
    with pytest.raises(SessionLimit, match="session_time_limit"):
        budget.check()


def test_audit_has_its_own_finite_allowance(tmp_path, monkeypatch):
    now = [0.0]
    monkeypatch.setattr("harness.agent.time.monotonic", lambda: now[0])
    def audit():
        now[0] += 2
        return {}
    with Trace(tmp_path / "trace.jsonl", "audit-limit") as trace:
        session = comparison_session(ScriptedClient(lambda *args: {"content": "done"}), trace, [], [],
            mode="single", domain_tools=(), workspace_audit=audit, session_seconds=5, audit_seconds=1)
        result = session.run("task")
    assert result.status == "done" and result.infra_affected
    assert any(e["type"] == "session_workspace_audit_skipped" and e["reason"] == "audit_time_limit"
               for e in read_trace(trace.path))


def paired_specs(tmp_path):
    result = {}
    for mode in ("single", "team"):
        result[mode] = dict(contract={key: "same" for key in (
            "task", "model", "tools", "common_prompt", "budgets", "pricing", "source_digest")},
            output=str(tmp_path / mode / "output"), archive=str(tmp_path / mode / "output/retained"),
            environment=dict(image_id="image", container_id=mode, dataset_files={"data": "hash"},
                resources={"Memory": 100}, network="none", mounts=[
                    {"Destination": "/data", "Source": str(tmp_path / "data")},
                    {"Destination": "/workspace", "Source": str(tmp_path / mode / "work")}]))
    return result


def test_real_pair_preflight_rejects_drift_and_shared_state(tmp_path):
    original = paired_specs(tmp_path)
    assert validate_pair(original)["sha256"]
    for key in ("image_id", "dataset_files", "resources"):
        arms = copy.deepcopy(original)
        arms["team"]["environment"][key] = "different"
        with pytest.raises(ValueError, match="differ"):
            validate_pair(arms)
    arms = copy.deepcopy(original)
    arms["team"]["contract"]["model"] = "different"
    with pytest.raises(ValueError, match="contract"):
        validate_pair(arms)
    arms = copy.deepcopy(original)
    arms["team"]["environment"]["container_id"] = "single"
    with pytest.raises(ValueError, match="different containers"):
        validate_pair(arms)
    arms = copy.deepcopy(original)
    arms["team"]["environment"]["mounts"][1]["Source"] = arms["single"]["environment"]["mounts"][1]["Source"]
    with pytest.raises(ValueError, match="workspaces overlap"):
        validate_pair(arms)
    arms = copy.deepcopy(original)
    arms["team"]["output"] = arms["single"]["output"]
    with pytest.raises(ValueError, match="namespaces"):
        validate_pair(arms)
