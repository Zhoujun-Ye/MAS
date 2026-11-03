"""CLI process transport and raw evidence; no model or team orchestration."""

import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time


def positive(value, name):
    if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be positive and finite")


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def verify_cli(executable, version, pattern, env, cwd, command_prefix=()):
    resolved = shutil.which(str(executable))
    if resolved is None:
        raise FileNotFoundError(f"CLI not installed: {executable}")
    resolved = str(Path(resolved).resolve(strict=True))
    probe = subprocess.run([*command_prefix, resolved, "--version"], cwd=cwd, env=env,
                           capture_output=True, text=True, timeout=30, check=True)
    match = re.search(pattern, probe.stdout, flags=re.MULTILINE)
    if match is None or match.group(1) != version:
        raise ValueError(f"Expected CLI version {version}; --version returned {probe.stdout.strip()!r}")
    return dict(executable=resolved, version=version, version_output=probe.stdout.strip(),
                launcher_sha256=hashlib.sha256(Path(resolved).read_bytes()).hexdigest())


def stop_process_group(process):
    # POSIX process groups cover ordinary CLI children, not detached services.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


def run_cli(*, backend, argv, version, version_pattern, environment, prompt,
            workspace, output, timeout, execute=False, parse_result=None, command_prefix=()):
    """Plan by default. Execution invokes an installed CLI once, without retries."""
    positive(timeout, "timeout")
    prompt = prompt.strip()
    if not prompt:
        raise ValueError("Prompt must not be empty")
    workspace = Path(workspace).resolve(strict=True)
    output = Path(output).resolve()
    if not workspace.is_dir():
        raise ValueError("Workspace must be a directory")
    if output.is_relative_to(workspace) or workspace.is_relative_to(output):
        raise ValueError("Workspace and output must not overlap")
    plan = dict(backend=backend, expected_version=version, argv=list(argv),
                command_prefix=list(command_prefix),
                workspace=str(workspace), output=str(output), timeout_seconds=timeout,
                environment_overrides=environment, prompt_characters=len(prompt),
                prompt_utf8_bytes=len(prompt.encode("utf-8")),
                prompt_sha256=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                adapter_retries=0, status="planned", model_calls_started=False)
    if not execute:
        return plan
    if os.name != "posix":
        raise RuntimeError("CLI process cleanup currently requires POSIX")
    # The fresh namespace protects earlier attempts, including failed preflights.
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "launch.json", plan)
    (output / "prompt.txt").write_text(prompt, encoding="utf-8")
    env = dict(os.environ, **environment)
    report = dict(backend=backend, status="preflight_error", returncode=None,
                  usage=None, cost_usd=None, team_created=None,
                  correctness="not_evaluated", model_calls_started=False)
    started, process = time.monotonic(), None
    try:
        verified = verify_cli(argv[0], version, version_pattern, env, workspace, command_prefix)
        write_json(output / "cli-version.json", verified)
        command = [*command_prefix, verified["executable"], *argv[1:]]
        with (output / "prompt.txt").open("rb") as stdin, \
                (output / "stdout.log").open("xb") as stdout, \
                (output / "stderr.log").open("xb") as stderr:
            process = subprocess.Popen(command, cwd=workspace, env=env, stdin=stdin,
                                       stdout=stdout, stderr=stderr, start_new_session=True)
            # Dispatch does not establish that the provider accepted any calls.
            report.update(status="running", model_calls_started=None)
            try:
                report["returncode"] = process.wait(timeout=timeout)
                report["status"] = "cli_exited" if process.returncode == 0 else "cli_error"
            except subprocess.TimeoutExpired:
                report["status"] = "timed_out"
            finally:
                stop_process_group(process)
                report["returncode"] = process.returncode
        if report["status"] == "cli_exited" and parse_result is not None:
            report.update(parse_result(output / "stdout.log"))
    except (KeyboardInterrupt, SystemExit):
        report["status"] = "interrupted"
        raise
    except Exception as error:
        if process is not None:
            report["status"] = "adapter_error"
        report["error"] = dict(type=type(error).__name__, message=str(error))
    finally:
        report["elapsed_seconds"] = time.monotonic() - started
        write_json(output / "result.json", report)
    return report
