import json
import hashlib
import threading
from types import SimpleNamespace

import pytest

from benchmarks.kramabench.tasks import Task
from benchmarks._io import fingerprint
from scripts.kramabench import cli_runtime as runtime
from scripts.kramabench import run


def bound_proof(backend):
    single = backend.endswith("single-agent")
    binding = dict(image_id="fixture-image", binary_sha256="fixture-binary-hash")
    proof = dict(backend=backend, passed=True, network="none", paid_calls=0,
                 runtime_binding=binding, shell_verified=True, tool_exposure_verified=True)
    if single:
        proof["native_single_agent"] = dict(passed=True, subagent_starts=0, executed_delegation_tools=0)
        proof["delegation_rejections_observed"] = 2
    else:
        proof["native_subagents"] = dict(passed=True, subagent_starts=1, native_team_configs=0, teammate_idle_events=0)
    plan = dict(image_id="fixture-image", cli_binaries={"claude": dict(sha256="fixture-binary-hash")},
                model_catalogs={})
    return proof, plan


@pytest.mark.parametrize("backend", ["claude-code-single-agent", "claude-code-subagents"])
def test_freeze_requires_runtime_bound_proof(tmp_path, monkeypatch, backend):
    proof, plan = bound_proof(backend)
    path = tmp_path / "proof.json"
    path.write_text(json.dumps(proof))
    task = Task("probe", "astronomy", "Fixture")
    plan["attempts"] = 1
    args = SimpleNamespace(backend=backend, offline_proof=path, output=tmp_path / "out")
    monkeypatch.setattr(runtime, "preflight", lambda args: ([task], dict(plan)))
    tasks, frozen = run.freeze(args)
    assert tasks == [task]
    assert frozen["offline_proof_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    proof["runtime_binding"]["image_id"] = "stale-image"
    path.write_text(json.dumps(proof))
    with pytest.raises(ValueError, match="Stale native proof"):
        run.freeze(args)


@pytest.mark.parametrize("changed_proof", [False, True])
def test_from_plan_revalidates_proof_binding(tmp_path, monkeypatch, changed_proof):
    backend = "claude-code-subagents"
    proof, plan = bound_proof(backend)
    path = tmp_path / "proof.json"
    if not changed_proof:
        proof["runtime_binding"]["binary_sha256"] = "stale-binary"
    path.write_text(json.dumps(proof))
    plan["offline_proof_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / "plan.json").write_text(json.dumps(plan))
    (tmp_path / "preflight-ok.json").write_text(json.dumps(dict(plan_sha256=fingerprint(plan))))
    if changed_proof:
        path.write_text(json.dumps(proof) + "\n")
    monkeypatch.setattr(run, "load_tasks", lambda *a: pytest.fail("Must reject proof before workload access"))
    args = SimpleNamespace(output=tmp_path, offline_proof=path, backend=backend)
    with pytest.raises(ValueError, match="Offline proof changed|Stale native proof"):
        run.validate(args)


@pytest.fixture(params=["claude-code-single-agent", "claude-code-subagents"])
def roundtrip_plan(request, tmp_path, monkeypatch):
    backend = request.param
    task = Task("probe", "astronomy", "Fixture")
    proof, plan = bound_proof(backend)
    binary = tmp_path / "native-cli"
    binary.write_text("fixture-binary")
    binary_hash = hashlib.sha256(binary.read_bytes()).hexdigest()
    name = "claude"
    plan["cli_binaries"][name] = dict(path=str(binary), sha256=binary_hash)
    proof["runtime_binding"]["binary_sha256"] = binary_hash
    proof_path = tmp_path / "proof.json"
    proof_path.write_text(json.dumps(proof))
    args = SimpleNamespace(backend=backend, backends=(backend,), output=tmp_path / "out",
        upstream=tmp_path, offline_proof=proof_path, all_tasks=False, selected_task_ids=[task.id],
        concurrency=1, timeout=3600, judge_limit=1, replay_timeout=180)
    plan.update(attempts=1, tasks=[dict(id=task.id, domain=task.domain, query=task.query)],
        organization_override=None, backend_instructions={backend: run.shared.condition_instructions(args, backend)},
        limit_instructions=run.shared.limit_instructions(3600),
        backend_options={backend: runtime.backend_options(args, backend)}, source={"fixture": "source-hash"},
        inputs_sha256=fingerprint({"fixture": "data-hash"}), scoring={"version": 1},
        concurrency=1, timeout_seconds=3600, judge_limit=1, replay_timeout_seconds=180)
    monkeypatch.setattr(runtime, "preflight", lambda args: ([task], plan.copy()))
    monkeypatch.setattr(run, "load_tasks", lambda path: ([task], {}))
    monkeypatch.setattr(run.shared, "source_manifest", lambda: {"fixture": "source-hash"})
    monkeypatch.setattr(runtime, "verify_inputs", lambda path: {"fixture": "data-hash"})
    monkeypatch.setattr(run, "scoring_contract", lambda path: {"version": 1})
    run.freeze(args)
    return args, task


def test_frozen_options_survive_json_roundtrip(roundtrip_plan):
    args, task = roundtrip_plan
    tasks, plan = run.validate(args)
    assert tasks == [task]
    if args.backend.startswith("claude-"):
        assert isinstance(plan["backend_options"][args.backend]["allowed_tools"], list)
        assert isinstance(runtime.backend_options(args, args.backend)["allowed_tools"], tuple)


def test_frozen_effort_cannot_change(roundtrip_plan):
    args, _ = roundtrip_plan
    args.effort = "high"
    with pytest.raises(ValueError, match="Frozen effort changed"):
        run.validate(args)


@pytest.mark.parametrize("change", ["model", "allowed_tools", "disallowed_tools", "source", "data", "scoring", "prompt", "timeout"])
def test_roundtrip_still_rejects_real_changes(roundtrip_plan, monkeypatch, change):
    args, _ = roundtrip_plan
    if change == "model":
        changed = dict(runtime.backend_options(args, args.backend), model="changed")
        monkeypatch.setattr(runtime, "backend_options", lambda *a: changed)
    elif change in {"allowed_tools", "disallowed_tools"}:
        changed = runtime.backend_options(args, args.backend)
        changed[change] = (*changed.get(change, ()), "ChangedTool")
        monkeypatch.setattr(runtime, "backend_options", lambda *a: changed)
    elif change == "source":
        monkeypatch.setattr(run.shared, "source_manifest", lambda: {"fixture": "changed"})
    elif change == "data":
        monkeypatch.setattr(runtime, "verify_inputs", lambda path: {"fixture": "changed"})
    elif change == "scoring":
        monkeypatch.setattr(run, "scoring_contract", lambda path: {"version": 2})
    elif change == "prompt":
        monkeypatch.setattr(run.shared, "condition_instructions", lambda *a: "changed")
    else:
        args.timeout += 1
    with pytest.raises(ValueError, match="Frozen condition/source/data/scoring changed|Frozen settings changed"):
        run.validate(args)


@pytest.mark.parametrize("removed", [True, False])
def test_startup_failure_preserves_owned_container(tmp_path, monkeypatch, removed):
    from scripts.common.runtime import ContainerStartupError
    captured = {}
    class Gateway:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            captured["closed"] = True
    details = dict(stopped=False, removed=removed, errors=["RuntimeError"])
    def failed(*args, **kwargs):
        raise ContainerStartupError("owned-fixture", details)
    monkeypatch.setattr(runtime, "CredentialGateway", Gateway)
    monkeypatch.setattr(runtime, "container", failed)
    monkeypatch.setattr(runtime.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0))
    args = SimpleNamespace(output=tmp_path / "out", upstream=tmp_path, image="fixture", timeout=900)
    active, stop = set(), threading.Event()
    report = runtime.run_attempt(Task("probe", "astronomy", "Fixture"), "claude-code-subagents", args,
        "synthetic-secret", stop, active, threading.Lock())
    assert report["container_id"] == "owned-fixture"
    assert report["startup_cleanup"] == details
    assert captured["closed"]
    assert ("owned-fixture" in active) is (not removed)
    assert stop.is_set() is (not removed)


def test_claude_subagents_without_delegation_is_not_admitted(tmp_path, monkeypatch):
    class Gateway:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
    class Adapter:
        def __init__(self, *args):
            pass
        def run(self, *args, **kwargs):
            return dict(status="cli_exited")
    monkeypatch.setattr(runtime, "CredentialGateway", Gateway)
    monkeypatch.setattr(runtime, "ClaudeCodeSubagentsCLI", Adapter)
    monkeypatch.setattr(runtime, "container", lambda *a, **kw: "fixture-container")
    monkeypatch.setattr(runtime, "stop_container", lambda *a: dict(stopped=True))
    monkeypatch.setattr(runtime.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0))
    monkeypatch.setattr(runtime, "native_subagents", lambda *a: dict(passed=False, native_team_configs=0, teammate_idle_events=0))
    args = SimpleNamespace(output=tmp_path / "out", upstream=tmp_path, image="fixture", timeout=900)
    report = runtime.run_attempt(Task("probe", "astronomy", "Fixture"), "claude-code-subagents", args,
        "synthetic-secret", threading.Event(), set(), threading.Lock())
    assert report["status"] == "native_condition_unverified"
