"""Ownership boundaries prevent benchmark-specific dependencies creeping back in."""

import ast
from pathlib import Path

from scripts.kramabench import prepare

ROOT = Path(__file__).resolve().parents[1]


def test_benchmarks_have_matching_public_entry_points():
    for name in ("kramabench", "dataclawbench", "hybriddeepresearch"):
        for module in ("tasks", "evaluation"):
            assert (ROOT / "benchmarks" / name / (module + ".py")).is_file()
        for command in ("catalog", "run", "score"):
            assert (ROOT / "scripts" / name / (command + ".py")).is_file()


def test_common_runtime_does_not_depend_on_a_benchmark_runner():
    for path in (ROOT / "scripts/common").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("scripts.kramabench")
    assert not (ROOT / "scripts/research_benchmarks").exists()


def test_image_preparation_is_plan_only_by_default(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(prepare, "verify_inputs", lambda _: dict(total_files=1, total_bytes=5))
    def forbid(*args, **kwargs):
        raise AssertionError("Planning must not launch Docker or provision an environment")
    monkeypatch.setattr(prepare.subprocess, "run", forbid)
    monkeypatch.setattr(prepare.subprocess, "check_output", forbid)
    monkeypatch.setattr(prepare.sys, "argv", ["prepare.py", "--upstream", str(tmp_path),
        "--output", str(tmp_path / "new"), "--base-image", "existing@sha256:fake", "--image", "new"])
    prepare.main()
    assert not (tmp_path / "new").exists()
    assert '"environment_changed": false' in capsys.readouterr().out
