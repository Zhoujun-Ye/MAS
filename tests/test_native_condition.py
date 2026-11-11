"""Native is an explicit prompt condition, not another runtime or a renamed Structured run."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.common.prompts.conditions import condition_instructions, backend_instructions
from scripts.common.prompts.native_subagents import PROMPT
from scripts.studies import benchmark_matrix as matrix
from scripts.studies.matched_matrix_report import collect, write_report


CONDITIONS = ("claude-code-single-agent", "native", "claude-code-subagents")


def test_native_is_exact_approved_prefix_and_delegation_requirement():
    structured = backend_instructions("claude-code-subagents")
    assert PROMPT == structured.split("\n\n", 1)[0] + "\n\nAlways deploy at least one subagent."
    assert condition_instructions(SimpleNamespace(subagents_prompt="native"), "claude-code-subagents") == PROMPT
    assert hashlib.sha256(structured.encode()).hexdigest() == "31ff6e4176a25d961866f644adb4d7b97cb4b00228e696c0e4e38a52b9485a95"


def test_committed_random20_protocol_matches_the_three_condition_runtime():
    import random
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "docs/studies/krama-random20-manifest.json").read_text())
    protocol = json.loads((root / "docs/studies/krama-random20-protocol.json").read_text())
    settings = matrix.protocol_settings(SimpleNamespace(backends=CONDITIONS, benchmarks=["kramabench"],
        effort="none", concurrency=16, judge_concurrency=2, cpus=8, compute_threads=4, record_resources=True))
    assert protocol == manifest["baseline_settings"] == settings
    assert manifest["sampling"]["seed"] == 6820760213620092556
    shuffled = list(manifest["sampling"]["population"]["kramabench"])
    assert len(shuffled) == 104
    random.Random(manifest["sampling"]["seed"]).shuffle(shuffled)
    assert manifest["benchmarks"]["kramabench"] == shuffled[:20]
    original = json.loads((root / "docs/studies/validation20-v1-manifest.json").read_text())
    old_ids = {r["task_id"] for r in original["benchmarks"]["kramabench"]}
    new_ids = {r["task_id"] for r in shuffled[:20]}
    assert len(new_ids) == 20 and len(new_ids & old_ids) == 4


@pytest.mark.parametrize("backend,override,preset", [
    ("claude-code-single-agent", None, "native"),
    ("claude-code-subagents", {"text": "override"}, "native"),
    ("claude-code-subagents", None, "unknown"),
])
def test_native_prompt_does_not_silently_override_another_condition(backend, override, preset):
    with pytest.raises(ValueError, match="Native prompt|Unknown Subagents"):
        condition_instructions(SimpleNamespace(subagents_prompt=preset, organization_override=override), backend)


def arguments(tmp_path, *extra):
    return ["--root", str(tmp_path), "--output", str(tmp_path / "out"),
            "--proofs", str(tmp_path / "proofs"), "--image", "fixture",
            "--benchmarks", "kramabench", "--conditions", *CONDITIONS, *extra]


def test_random20_plan_has_sixty_independent_slots_without_credentials(tmp_path, monkeypatch, capsys):
    tasks = [("kramabench", SimpleNamespace(id=f"fixture-{i}", query="public")) for i in range(20)]
    monkeypatch.setattr(matrix, "selections", lambda *a: tasks)
    monkeypatch.setattr(matrix.runtime, "credential", lambda *a: pytest.fail("Plan loaded credentials"))
    monkeypatch.setattr(matrix.subprocess, "Popen", lambda *a, **kw: pytest.fail("Plan launched a process"))
    assert matrix.main(arguments(tmp_path, "--tasks-per-benchmark", "20", "--concurrency", "16")) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["attempts"] == 60 and plan["solver_concurrency"] == 16 and plan["retries"] == 0
    assert plan["selections"][:3] == [dict(benchmark="kramabench", task_id="fixture-0", backend=k) for k in CONDITIONS]
    assert plan["protocol_settings"]["organization_sha256"]["native"] == hashlib.sha256(PROMPT.encode()).hexdigest()
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("condition", CONDITIONS)
def test_child_commands_separate_preset_from_underlying_runtime(tmp_path, condition):
    args = SimpleNamespace(root=tmp_path, proofs=tmp_path / "proofs", image="fixture",
                           credentials=tmp_path / "private.env", cpus=8, compute_threads=4)
    backend = matrix.runtime_backend(condition)
    cmd = matrix.solver_command(args, "kramabench", SimpleNamespace(id="fixture"), condition, tmp_path / condition)
    assert cmd[cmd.index("--backend") + 1] == backend
    assert cmd[cmd.index("--offline-proof") + 1] == str(args.proofs / backend / "proof.json")
    assert ("--subagents-prompt" in cmd) is (condition == "native")
    if condition == "native":
        assert cmd[cmd.index("--subagents-prompt") + 1] == "native"
    assert cmd[cmd.index("--cpus") + 1] == "8" and cmd[cmd.index("--compute-threads") + 1] == "4"


def test_native_and_structured_have_identical_infra_commands(tmp_path):
    args = SimpleNamespace(root=tmp_path, proofs=tmp_path / 'proofs', image='immutable-image',
        credentials=tmp_path / 'private.env', cpus=8, compute_threads=4, effort='max', record_resources=True)
    task = SimpleNamespace(id='same-task')
    native = matrix.solver_command(args, 'kramabench', task, 'native', tmp_path / 'native', execute=True)
    structured = matrix.solver_command(args, 'kramabench', task, 'claude-code-subagents', tmp_path / 'structured', execute=True)
    position = native.index('--subagents-prompt')
    assert native[position + 1] == 'native'
    del native[position:position + 2]
    for command in (native, structured):
        command[command.index('--output') + 1] = 'isolated-output'
    assert native == structured


def test_native_scope_rejects_other_benchmarks_before_loading_credentials(tmp_path, monkeypatch):
    monkeypatch.setattr(matrix.runtime, "credential", lambda *a: pytest.fail("Invalid scope loaded credentials"))
    with pytest.raises(ValueError, match="scoped to KramaBench"):
        matrix.main(arguments(tmp_path, "--benchmarks", "dataclawbench"))


def test_standalone_native_rejects_single_before_workload_or_proof_access(tmp_path, monkeypatch):
    from scripts.kramabench import run
    monkeypatch.setattr(run, "load_tasks", lambda *a: pytest.fail("Invalid condition read tasks"))
    with pytest.raises(ValueError, match="Native prompt requires Subagents"):
        run.main(["--backend", "claude-code-single-agent", "--subagents-prompt", "native",
                  "--upstream", str(tmp_path), "--output", str(tmp_path / "out"),
                  "--offline-proof", str(tmp_path / "unused.json")])


def test_controller_journal_grades_and_report_keep_native_separate(tmp_path, monkeypatch):
    tasks = [("kramabench", SimpleNamespace(id=f"fixture-{i}", query="public")) for i in range(2)]
    monkeypatch.setattr(matrix, "selections", lambda *a: tasks)
    monkeypatch.setattr(matrix, "runtime_preflight", lambda *a: dict(image_id="fixture"))
    monkeypatch.setattr(matrix.runtime, "source_manifest", lambda: {"fixture.py": "same"})
    monkeypatch.setattr(matrix.runtime, "credential", lambda *a: "synthetic-only")
    monkeypatch.setattr(matrix.runtime, "safe_balance", lambda *a: dict(response=dict(is_available=True,
        balance_infos=[dict(currency="CNY", total_balance="100")])))
    launched = []

    class Process:
        def __init__(self, cmd, **kwargs):
            if "--execute" not in cmd:
                return
            out = Path(cmd[cmd.index("--output") + 1])
            task = cmd[cmd.index("--task-id") + 1]
            backend = cmd[cmd.index("--backend") + 1]
            folder = out / task / backend
            folder.mkdir(parents=True)
            (folder / "report.json").write_text(json.dumps(dict(status="cli_exited", cli=dict(elapsed_seconds=1))))
            (folder / "submission.json").write_text('{"answer":1}')
            (out / "summary.json").write_text('{"rows":[]}')
            (out / "plan.json").write_text(json.dumps(dict(backend_instructions={backend:
                PROMPT if out.name == 'native' else backend_instructions(backend)})))
            launched.append(out)

        def wait(self, **kwargs):
            return 0

    def grade(b, t, backend, run, **kwargs):
        condition = run.name
        assert backend == matrix.runtime_backend(condition)
        expected = tmp_path / "out/grades"
        if condition == "native":
            expected /= "native"
        assert kwargs["grades_root"] == expected
        return dict(benchmark=b, task_id=t.id, backend=backend, status="graded", judge_calls=0,
                    grade=dict(status="graded", score=0 if condition == "native" else 1))

    monkeypatch.setattr(matrix.subprocess, "Popen", Process)
    monkeypatch.setattr(matrix, "grade_attempt", grade)
    assert matrix.main(arguments(tmp_path, "--authorized-attempts", "6", "--estimated-cost", "1", "--execute")) == 0
    summary = json.loads((tmp_path / "out/summary.json").read_text())
    assert len(launched) == len(set(launched)) == len(summary["grades"]) == 6
    assert {g["backend"] for g in summary["grades"]} == set(CONDITIONS)
    native = [g for g in summary["grades"] if g["backend"] == "native"]
    assert all("/grades/native/" in g["grading_artifact"] for g in native)
    for row in summary['rows']:
        if row['backend'] == 'native':
            row.pop('runtime_backend')
    (tmp_path / 'out/summary.json').write_text(json.dumps(summary))
    report = collect(tmp_path / "out")
    assert all(r["score"] == (0 if r["backend"] == "native" else 1) for r in report["rows"])
    assert all(r["evidence"].endswith("/claude-code-subagents") for r in report["rows"] if r["backend"] == "native")
    assert all(r['prompt']['organization_characters'] == len(PROMPT) for r in report['rows'] if r['backend'] == 'native')
    assert {g["backend"] for g in report["groups"] if g["benchmark"] == "kramabench"} == set(CONDITIONS)
    write_report(report, tmp_path / "report")
    assert "| Native |" in (tmp_path / "report/REPORT.md").read_text()
    assert "| Structured |" in (tmp_path / "report/REPORT.md").read_text()
