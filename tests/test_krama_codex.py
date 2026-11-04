import json
import hashlib
import threading
from types import SimpleNamespace

import pytest

from benchmarks.kramabench.tasks import Task
from benchmarks._io import fingerprint
from scripts.kramabench import cli_runtime as runtime
from scripts.kramabench import run


@pytest.mark.parametrize("backend", ["codex-single-agent", "codex-subagents"])
@pytest.mark.parametrize("passed", [True, False])
def test_codex_attempt_uses_gateway_and_native_evidence(tmp_path, monkeypatch, backend, passed):
    captured = {}

    class Gateway:
        url = "http://127.0.0.1:8765"
        def __init__(self, key, **kwargs):
            assert key == "synthetic-secret" and kwargs["web_limit"] == 0
        def __enter__(self):
            return self
        def __exit__(self, *args):
            captured["gateway_closed"] = True

    class Adapter:
        def __init__(self, binary):
            assert binary == str(runtime.CODEX)
        def run(self, prompt, **kwargs):
            captured.update(kwargs)
            return dict(status="cli_exited")

    def container(*args, **kwargs):
        assert len(args) == 4 and "key" not in kwargs
        assert isinstance(kwargs["gateway"], Gateway)
        return "fixture-container"

    monkeypatch.setattr(runtime, "CredentialGateway", Gateway)
    monkeypatch.setattr(runtime, "CodexSingleAgentCLI", Adapter)
    monkeypatch.setattr(runtime, "CodexSubagentsCLI", Adapter)
    monkeypatch.setattr(runtime, "container", container)
    monkeypatch.setattr(runtime, "codex_evidence", lambda path, single: dict(passed=passed, single=single))
    monkeypatch.setattr(runtime, "stop_container", lambda identity: dict(stopped=True))
    monkeypatch.setattr(runtime.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0))
    args = SimpleNamespace(output=tmp_path / "outputs", upstream=tmp_path, image="fake", timeout=900,
                           codex_docker_isolated=True)
    active = set()
    report = runtime.run_attempt(Task("probe", "astronomy", "Fixture"), backend, args,
        "synthetic-secret", threading.Event(), active, threading.Lock())
    assert captured["base_url"] == Gateway.url
    assert captured["docker_isolated"] is True
    assert captured["timeout"] == 900
    assert captured["profile_target"] == "/native/codex"
    assert "observer_dir" not in captured
    assert captured["gateway_closed"]
    assert not active
    assert report["native_codex"]["single"] == backend.endswith("single-agent")
    assert report["status"] == ("cli_exited" if passed else "native_condition_unverified")
    assert "synthetic-secret" not in json.dumps(report)


@pytest.mark.parametrize("backend", ["codex-single-agent", "codex-subagents"])
def test_codex_admission_uses_codex_reader(tmp_path, monkeypatch, backend):
    monkeypatch.setattr(runtime, "submission", lambda path: {})
    monkeypatch.setattr(run, "codex_evidence", lambda path, single: dict(passed=True, single=single))
    assert not hasattr(run, "native_team")
    audit = run.admission(tmp_path, dict(task_id="probe", backend=backend, status="cli_exited"))
    assert audit["passed"]
    assert audit["native_codex"]["single"] == backend.endswith("single-agent")


def test_codex_cli_parse_and_default_timeout(tmp_path, monkeypatch):
    task = Task("probe", "astronomy", "Fixture")
    monkeypatch.setattr(run, "load_tasks", lambda path: ([task], {}))
    captured = {}
    def freeze(args):
        captured.update(vars(args))
        return [task], {}
    monkeypatch.setattr(run, "freeze", freeze)
    run.main(["--backend", "codex-subagents", "--task-id", "probe", "--upstream", str(tmp_path),
              "--output", str(tmp_path / "out"), "--offline-proof", str(tmp_path / "proof.json"),
              "--codex-docker-isolated"])
    assert captured["timeout"] == 3600
    assert captured["codex_docker_isolated"]
    assert runtime.backend_options(SimpleNamespace(codex_docker_isolated=True), "codex-subagents")["docker_isolated"]


def test_codex_preflight_freezes_binary_catalog_and_sandbox(tmp_path, monkeypatch):
    task = Task("probe", "astronomy", "Fixture")
    binary, catalog = tmp_path / "codex", tmp_path / "deepseek-models.json"
    binary.write_text("fixture-binary")
    catalog.write_text("{}")
    single_catalog = catalog.with_name("deepseek-single-models.json")
    single_catalog.write_text('{"multi_agent_version":null}')
    monkeypatch.setattr(runtime, "CODEX", binary)
    monkeypatch.setattr(runtime, "CODEX_CATALOG", catalog)
    monkeypatch.setattr(runtime, "load_tasks", lambda path: ([task], {}))
    monkeypatch.setattr(runtime, "scoring_contract", lambda path: {})
    monkeypatch.setattr(runtime, "verify_inputs", lambda path: {})
    monkeypatch.setattr(runtime, "source_manifest", lambda: {})
    monkeypatch.setattr(runtime, "source_files", lambda: iter(()))
    captured = {}
    def container(*args, **kwargs):
        captured.update(kwargs)
        return "fixture-container"
    monkeypatch.setattr(runtime, "container", container)
    monkeypatch.setattr(runtime, "stop_container", lambda *a: {})
    monkeypatch.setattr(runtime.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0))
    monkeypatch.setattr(runtime.subprocess, "check_output", lambda command, **kwargs:
        '[{"Id":"fixture-image"}]' if command[:3] == ["docker", "image", "inspect"] else "fixture-version")
    args = SimpleNamespace(upstream=tmp_path, output=tmp_path / "out", selected_task_ids=[task.id],
        backends=("codex-single-agent",), image="fake", concurrency=1, timeout=900, codex_docker_isolated=True)
    selected, plan = runtime.preflight(args)
    assert selected == [task]
    assert set(plan["cli_binaries"]) == {"codex"}
    assert plan["model_catalogs"]["codex-single-agent"]["path"] == str(single_catalog)
    assert plan["backend_options"]["codex-single-agent"]["docker_isolated"]
    assert plan["strict_single"]
    assert captured["backend"] == "codex-single-agent" and captured["network"] == "none"


def bound_proof(backend):
    codex = backend.startswith("codex-")
    single = backend.endswith("single-agent")
    binding = dict(image_id="fixture-image", binary_sha256="fixture-binary-hash")
    if codex:
        binding["catalog_sha256"] = "fixture-catalog-hash"
    proof = dict(backend=backend, passed=True, network="none", paid_calls=0,
                 runtime_binding=binding, shell_verified=True, tool_exposure_verified=True)
    if codex:
        proof["native_codex"] = dict(passed=True, subagent_starts=0 if single else 1)
    elif single:
        proof["native_single_agent"] = dict(passed=True, subagent_starts=0, executed_delegation_tools=0)
        proof["delegation_rejections_observed"] = 2
    else:
        proof["native_subagents"] = dict(passed=True, subagent_starts=1, native_team_configs=0, teammate_idle_events=0)
    plan = dict(image_id="fixture-image", cli_binaries={"codex" if codex else "claude": dict(sha256="fixture-binary-hash")},
                model_catalogs={backend: dict(sha256="fixture-catalog-hash")} if codex else {})
    return proof, plan


@pytest.mark.parametrize("backend", ["claude-code-single-agent", "claude-code-subagents", "codex-single-agent", "codex-subagents"])
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
    backend = "codex-subagents"
    proof, plan = bound_proof(backend)
    path = tmp_path / "proof.json"
    if not changed_proof:
        proof["runtime_binding"]["catalog_sha256"] = "stale-catalog"
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


@pytest.fixture(params=["claude-code-single-agent", "claude-code-subagents", "codex-single-agent", "codex-subagents"])
def roundtrip_plan(request, tmp_path, monkeypatch):
    backend = request.param
    task = Task("probe", "astronomy", "Fixture")
    proof, plan = bound_proof(backend)
    binary = tmp_path / "native-cli"
    binary.write_text("fixture-binary")
    binary_hash = hashlib.sha256(binary.read_bytes()).hexdigest()
    name = "codex" if backend.startswith("codex-") else "claude"
    plan["cli_binaries"][name] = dict(path=str(binary), sha256=binary_hash)
    proof["runtime_binding"]["binary_sha256"] = binary_hash
    if backend.startswith("codex-"):
        catalog = tmp_path / "catalog.json"
        catalog.write_text("{}")
        catalog_hash = hashlib.sha256(catalog.read_bytes()).hexdigest()
        plan["model_catalogs"][backend] = dict(path=str(catalog), sha256=catalog_hash)
        proof["runtime_binding"]["catalog_sha256"] = catalog_hash
    proof_path = tmp_path / "proof.json"
    proof_path.write_text(json.dumps(proof))
    args = SimpleNamespace(backend=backend, backends=(backend,), output=tmp_path / "out",
        upstream=tmp_path, offline_proof=proof_path, all_tasks=False, selected_task_ids=[task.id],
        codex_docker_isolated=True, concurrency=1, timeout=3600, judge_limit=1, replay_timeout=180)
    plan.update(attempts=1, tasks=[dict(id=task.id, domain=task.domain, query=task.query)],
        organization_override=None, backend_instructions={backend: run.shared.condition_instructions(args, backend)},
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
    args = SimpleNamespace(output=tmp_path / "out", upstream=tmp_path, image="fixture")
    active, stop = set(), threading.Event()
    report = runtime.run_attempt(Task("probe", "astronomy", "Fixture"), "codex-subagents", args,
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
