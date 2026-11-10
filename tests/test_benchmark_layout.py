"""Ownership boundaries prevent benchmark-specific dependencies creeping back in."""

import ast
import tomllib
from pathlib import Path

from scripts.kramabench import prepare

ROOT = Path(__file__).resolve().parents[1]


def test_current_project_and_runtime_names_are_mas():
    assert tomllib.loads((ROOT/'pyproject.toml').read_text())['project']['name'] == 'mas'
    assert (ROOT/'README.md').read_text().splitlines()[0] == '# MAS'
    assert 'purpose=mas-cli6' in (ROOT/'harness/runtime_support/runtime.py').read_text()
    for name in ('evidence_mas',):
        assert 'mas/research-benchmarks:' in (ROOT/'scripts/probes'/(name+'.py')).read_text()


def test_temporary_three_question_runners_are_retired():
    for path in ('scripts/probes/evidence_paid.py','scripts/probes/evidence_tasks.py',
                 'scripts/studies/evidence_wrong_pairs.py'):
        assert not (ROOT/path).exists()


def test_benchmarks_have_matching_public_entry_points():
    for name in ("kramabench", "dataclawbench", "hybriddeepresearch", "fdabench"):
        for module in ("tasks", "evaluation"):
            assert (ROOT / "benchmarks" / name / (module + ".py")).is_file()
        for command in ("catalog", "run", "score"):
            assert (ROOT / "scripts" / name / (command + ".py")).is_file()


def test_server_access_has_one_key_based_entry_point_and_host_only_example():
    assert not (ROOT / 'scripts/server/ssh.exp').exists()
    remote = (ROOT / 'scripts/server/remote.sh').read_text()
    assert 'BatchMode=yes' in remote
    example = (ROOT / '.env.example').read_text()
    keys = [line.split('=', 1)[0] for line in example.splitlines() if line and not line.startswith('#')]
    assert keys == ['DEEPSEEK_API_KEY']


def test_common_runtime_does_not_depend_on_a_benchmark_runner():
    for path in (ROOT / "scripts/common").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("scripts.kramabench")
    assert not (ROOT / "scripts/research_benchmarks").exists()


def test_reusable_mas_and_tool_components_belong_to_harness():
    assert not (ROOT / 'scripts/studies/evidence_subagents/store.py').exists()
    for name in ('tools', 'credential_gateway', 'gateway_bridge', 'proof'):
        assert (ROOT / 'harness/runtime_support' / (name + '.py')).is_file()
        assert not (ROOT / 'scripts/common' / (name + '.py')).exists()
    for folder in ('evidence_mas', 'runtime_support'):
        for path in (ROOT / 'harness' / folder).glob('*.py'):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.ImportFrom):
                    assert not (node.module or '').startswith(('scripts', 'benchmarks'))


def test_retired_workflows_are_not_active_entry_points():
    for name in ('scripts/analyze.py', 'analysis/runs.py', 'analysis/legacy_trace.py',
                 'analysis/codex_evidence.py', 'scripts/studies/compare_subagents.py',
                 'scripts/studies/compare_claude_single.py', 'scripts/kramabench/results.py',
                 'scripts/kramabench/retain_current.py', 'scripts/server/retire_codex_results.py',
                 'scripts/server/retire_sources.py', 'scripts/server/cleanup_results.py',
                 'benchmarks/organization.py', 'scripts/studies/scoped_subagents_pilot.py',
                 'analysis/scoped_judge_audit.py', 'analysis/native_delegation_audit.py',
                 'docs/prompts/subagents-evidence-judge-v1.md', 'docs/history'):
        assert not (ROOT / name).exists()


def test_shared_layers_have_no_reverse_dependencies():
    for folder, forbidden in (("common", ("harness", "benchmarks", "analysis", "scripts")),
                              ("harness", ("benchmarks", "scripts")),
                              ("benchmarks", ("scripts",))):
        for path in (ROOT / folder).rglob('*.py'):
            for node in ast.walk(ast.parse(path.read_text())):
                modules = ([node.module or ''] if isinstance(node, ast.ImportFrom) else
                           [alias.name for alias in node.names] if isinstance(node, ast.Import) else [])
                assert not any(m == f or m.startswith(f + '.') for m in modules for f in forbidden), str(path)


def test_relocated_sources_have_one_owner():
    for old, new in (
        ('benchmarks/_io.py', 'common/io.py'),
        ('scripts/common/runtime.py', 'harness/runtime_support/runtime.py'),
        ('scripts/common/timeouts.py', 'benchmarks/policy.py'),
        ('scripts/server/benchmark_matrix.py', 'scripts/studies/benchmark_matrix.py'),
        ('scripts/server/offline_benchmarks.py', 'scripts/probes/offline_benchmarks.py'),
        ('scripts/server/offline_gateway.py', 'scripts/probes/offline_gateway.py'),
    ):
        assert not (ROOT / old).exists()
        assert (ROOT / new).is_file()


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
