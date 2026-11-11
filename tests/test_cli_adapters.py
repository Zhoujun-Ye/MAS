"""Offline process/argument checks; never invoke a real agent CLI."""

import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from harness import ClaudeCodeSubagentsCLI, ClaudeCodeSingleAgentCLI
from harness.__main__ import main


@pytest.fixture
def workspace(tmp_path):
    path = tmp_path / "workspace"
    path.mkdir()
    return path


@pytest.fixture
def stub(tmp_path):
    def build(*, version=None, stdout=None, exit_code=0, delay=0, child=False):
        version = version or "2.1.286 (Claude Code)"
        if stdout is None:
            stdout = json.dumps(dict(type="result", subtype="success", is_error=False,
                                     result="native reply")) + "\n"
        script = tmp_path / "stub-claude"
        script.write_text(f'''#!{sys.executable}
import json, os, subprocess, sys, time
from pathlib import Path
if '--version' in sys.argv:
    print({version!r})
    sys.exit(0)
record = dict(argv=sys.argv[1:], prompt=sys.stdin.read(), cwd=os.getcwd(),
              team=os.environ.get('CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS'),
              retries=os.environ.get('CLAUDE_CODE_MAX_RETRIES'))
if {child!r}:
    worker = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
    record['child_pid'] = worker.pid
Path('invocation.json').write_text(json.dumps(record))
print({stdout!r}, end='', flush=True)
sys.stderr.write('stub stderr\\n')
sys.stderr.flush()
time.sleep({delay!r})
sys.exit({exit_code!r})
''')
        script.chmod(0o755)
        return ClaudeCodeSubagentsCLI(str(script))
    return build


@pytest.mark.parametrize("adapter", [ClaudeCodeSubagentsCLI(), ClaudeCodeSingleAgentCLI()])
def test_default_is_side_effect_free_plan(adapter, workspace, tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Planning must not launch any subprocess")
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    output = tmp_path / "output"
    plan = adapter.run("task", model="explicit-model", workspace=workspace, output=output)
    assert plan["status"] == "planned" and plan["model_calls_started"] is False
    assert not output.exists() and list(workspace.iterdir()) == []
    assert "task" not in plan["argv"]


def test_native_deepseek_options_and_transport_plan(workspace, tmp_path):
    plan = ClaudeCodeSubagentsCLI().run("task", model="deepseek-flash[1m]", workspace=workspace,
        output=tmp_path / "out", command_prefix=("docker", "exec", "-i", "owned-container"))
    assert plan["command_prefix"] == ["docker", "exec", "-i", "owned-container"]
    assert "--print" in plan["argv"]
    command = ClaudeCodeSubagentsCLI().command("deepseek-flash[1m]", isolated_settings=True,
                                               disallowed_tools=("WebSearch", "WebFetch"))
    assert command[command.index("--setting-sources") + 1] == ""
    assert "--strict-mcp-config" in command


def test_subagent_command_uses_print_mode_and_native_permissions():
    command = ClaudeCodeSubagentsCLI().command("chosen-model", allowed_tools=("Read", "Edit"),
                                             max_budget_usd=0.5)
    assert command[:5] == ["claude", "--print", "--verbose", "--output-format", "stream-json"]
    settings = json.loads(command[command.index("--settings") + 1])
    assert settings == dict(env=dict(CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS="0"))
    assert command[-4:] == ["--allowedTools", "Read,Edit", "--max-budget-usd", "0.5"]
    assert "--dangerously-skip-permissions" not in command and "--agents" not in command


@pytest.mark.parametrize("adapter", [ClaudeCodeSubagentsCLI(), ClaudeCodeSingleAgentCLI()])
@pytest.mark.parametrize("model", ["", " ", "--fake-option"])
def test_model_is_required_and_not_an_option(adapter, model):
    with pytest.raises(ValueError):
        adapter.command(model)


@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan"), True])
def test_invalid_timeouts_rejected(value, workspace, tmp_path):
    with pytest.raises(ValueError):
        ClaudeCodeSubagentsCLI().run("task", model="model", workspace=workspace,
                            output=tmp_path / "out", timeout=value)


@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan"), True])
def test_invalid_native_budget_rejected(value):
    with pytest.raises(ValueError):
        ClaudeCodeSubagentsCLI().command("model", max_budget_usd=value)


def test_native_process_receipts_and_private_environment(stub, workspace, tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_PROVIDER_TOKEN", "must-not-appear-in-receipts")
    output = tmp_path / "output"
    prompt = "  task; $(touch DO_NOT_CREATE)\nkeep exact body  "
    report = stub().run(prompt, model="chosen-model", workspace=workspace,
                               output=output, execute=True)
    assert report["status"] == "cli_exited" and report["returncode"] == 0
    assert report["correctness"] == "not_evaluated" and report["team_created"] is None
    assert report["usage"] is None and report["cost_usd"] is None
    record = json.loads((workspace / "invocation.json").read_text())
    assert record["prompt"] == prompt.strip()
    assert record["cwd"] == str(workspace)
    assert not (workspace / "DO_NOT_CREATE").exists()
    assert (output / "prompt.txt").read_text() == prompt.strip()
    assert (output / "stderr.log").read_bytes() == b"stub stderr\n"
    assert "must-not-appear" not in "".join(p.read_text() for p in output.iterdir())
    version = json.loads((output / "cli-version.json").read_text())
    assert len(version["launcher_sha256"]) == 64
    assert record["team"] == "0" and record["retries"] == "0"
    assert report["native_result"]["result"] == "native reply"
    assert all(value is not None and value >= 0 for value in report['timing'].values())
    assert sum(report['timing'].values()) <= report['elapsed_seconds']
    before = {p.name: p.read_bytes() for p in output.iterdir()}
    with pytest.raises(FileExistsError):
        stub().run("new", model="model", workspace=workspace, output=output, execute=True)
    assert before == {p.name: p.read_bytes() for p in output.iterdir()}


def test_version_mismatch_stops_before_dispatch(stub, workspace, tmp_path):
    adapter = stub(version="9.0.0 (Claude Code)")
    report = adapter.run("task", model="model", workspace=workspace,
                         output=tmp_path / "out", execute=True)
    assert report["status"] == "preflight_error" and report["model_calls_started"] is False
    assert not (workspace / "invocation.json").exists()
    assert "Expected CLI version" in report["error"]["message"]


def test_missing_cli_leaves_failure_evidence(workspace, tmp_path):
    output = tmp_path / "out"
    result = ClaudeCodeSubagentsCLI(str(tmp_path / "missing")).run(
        "task", model="model", workspace=workspace, output=output, execute=True)
    assert result["status"] == "preflight_error"
    assert json.loads((output / "result.json").read_text())["error"]["type"] == "FileNotFoundError"


@pytest.mark.parametrize("stdout,status", [
    ("", "cli_protocol_error"), ("not-json\n", "cli_protocol_error"),
    ('{"type":"assistant","message":{}}\n', "cli_protocol_error"),
    ('{"type":"result","subtype":"error_max_turns","is_error":true}\n', "cli_error"),
    ('{"type":"result"}\n', "cli_error"),
])
def test_claude_final_text_is_not_silent_completion(stdout, status, stub, workspace, tmp_path):
    report = stub(stdout=stdout).run("task", model="model", workspace=workspace,
                                              output=tmp_path / "out", execute=True)
    assert report["status"] == status
    assert (tmp_path / "out/stdout.log").read_text() == stdout


def test_nonzero_exit_keeps_raw_logs(stub, workspace, tmp_path):
    report = stub(exit_code=7).run("task", model="model", workspace=workspace,
                                                output=tmp_path / "out", execute=True)
    assert report["status"] == "cli_error" and report["returncode"] == 7
    assert "native reply" in (tmp_path / "out/stdout.log").read_text()


def test_native_accounting_is_preserved_without_imputing_role_coverage(stub, workspace, tmp_path):
    event = dict(type="result", subtype="success", is_error=False,
                 usage=dict(input_tokens=120, output_tokens=30), total_cost_usd=0.002)
    report = stub(stdout=json.dumps(event) + "\n").run(
        "task", model="model", workspace=workspace, output=tmp_path / "out", execute=True)
    assert report["usage"] == event["usage"] and report["cost_usd"] == 0.002
    assert report["accounting_scope"] == "native_result; subagent usage coverage unverified"
    assert report["team_created"] is None


def test_blank_prompt_does_not_dispatch(stub, workspace, tmp_path):
    with pytest.raises(ValueError, match="Prompt"):
        stub().run(" \n ", model="model", workspace=workspace,
                               output=tmp_path / "out", execute=True)
    assert not (tmp_path / "out").exists()


def test_timeout_stops_process_group_and_preserves_partial_output(stub, workspace, tmp_path):
    report = stub(delay=60, child=True).run(
        "task", model="model", workspace=workspace, output=tmp_path / "out", timeout=0.5, execute=True)
    assert report["status"] == "timed_out" and report["returncode"] < 0
    assert report['timing']['native_process_seconds'] >= .5
    assert report['timing']['process_cleanup_seconds'] >= 0
    assert report['timing']['result_parse_seconds'] is None
    assert "native reply" in (tmp_path / "out/stdout.log").read_text()
    pid = json.loads((workspace / "invocation.json").read_text())["child_pid"]
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        # An unreaped child zombie has stopped executing too.
        stat = Path(f"/proc/{pid}/stat")
        if stat.exists() and stat.read_text().split()[2] == "Z":
            break
        time.sleep(0.02)
    else:
        pytest.fail("CLI descendant survived process-group cleanup")


def test_interrupt_is_recorded_and_propagated(stub, workspace, tmp_path, monkeypatch):
    original = subprocess.Popen.wait
    interrupted = False
    def wait(process, *args, **kwargs):
        nonlocal interrupted
        if "--version" not in process.args and not interrupted:
            interrupted = True
            raise KeyboardInterrupt
        return original(process, *args, **kwargs)
    monkeypatch.setattr(subprocess.Popen, "wait", wait)
    with pytest.raises(KeyboardInterrupt):
        stub(delay=60).run("task", model="model", workspace=workspace,
                                        output=tmp_path / "out", execute=True)
    assert json.loads((tmp_path / "out/result.json").read_text())["status"] == "interrupted"


@pytest.mark.parametrize("location", ["inside", "ancestor", "equal"])
def test_output_must_not_overlap_workspace(location, workspace):
    output = {"inside": workspace / "out", "ancestor": workspace.parent, "equal": workspace}[location]
    with pytest.raises(ValueError, match="overlap"):
        ClaudeCodeSubagentsCLI().run("task", model="model", workspace=workspace, output=output)


def test_main_plans_without_cli_and_rejects_cross_backend_flags(workspace, tmp_path, capsys):
    prompt = tmp_path / "task.txt"
    prompt.write_text("task")
    args = ["claude-code-subagents", "--workspace", str(workspace), "--output", str(tmp_path / "out"),
            "--prompt-file", str(prompt), "--model", "provider:model"]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "planned"
    with pytest.raises(SystemExit):
        main(args + ["--shell-allow-list", "python"])


def test_no_direct_provider_or_custom_runtime_dependencies():
    import tomllib
    root = Path(__file__).resolve().parents[1]
    config = tomllib.loads((root / "pyproject.toml").read_text())
    assert config["project"]["dependencies"] == []
    assert not (root / "harness/team.py").exists()
    assert not (root / "harness/llm.py").exists()
    assert not (root / "scripts/kramabench/pilot.py").exists()
