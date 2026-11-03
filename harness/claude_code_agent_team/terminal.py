"""Transport an interactive native CLI through a controlling terminal."""

import hashlib
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import time

from .._cli import positive, stop_process_group, verify_cli, write_json


def lifecycle_state(path):
    events = []
    if path.exists():
        for line in path.read_text(errors="replace").splitlines():
            try:
                events.append(json.loads(line))
            except ValueError:
                continue
    root_session, last_stop, last_worker_stop, activity = None, -1, -1, -1
    active, labels, root_end, last_message, stop_at = set(), {}, False, None, None
    for index, event in enumerate(events):
        kind = event.get("hook_event_name")
        if kind == "SessionStart" and root_session is None:
            root_session = event.get("session_id")
        identifier = event.get("agent_id") or event.get("agentId")
        worker_path = "/subagents/" in str(event.get("transcript_path", ""))
        root = not identifier and not worker_path and event.get("session_id") == root_session
        if kind == "SubagentStart" and identifier:
            active.add(identifier)
            labels[identifier] = event.get("agent_type")
            activity = index
        elif kind == "SubagentStop" and identifier:
            active.discard(identifier)
            last_worker_stop = index
        elif kind == "TeammateIdle":
            name = event.get("teammate_name")
            active.difference_update(i for i, label in labels.items() if label == name)
            last_worker_stop = index
        elif kind == "PostToolUse" and event.get("tool_name") == "SendMessage":
            arguments = event.get("tool_input") or {}
            message = arguments.get("message") if isinstance(arguments.get("message"), dict) else arguments
            if message.get("type") == "shutdown_response" and message.get("approve") is True:
                if identifier:
                    active.discard(identifier)
                active.difference_update(i for i, label in labels.items() if label == event.get("agent_type"))
                last_worker_stop = index
        elif kind == "Stop" and root:
            last_stop = index
            last_message = event.get("last_assistant_message")
            stop_at = event.get("observer_received_at")
        elif kind == "SessionEnd" and root:
            root_end = True
        elif kind == "UserPromptSubmit" and root:
            activity = index
        elif kind == "PreToolUse" and root:
            activity = index
    return dict(session_id=root_session, events=len(events), active_subagent_ids=sorted(active),
                root_stop_observed=last_stop >= 0, root_session_end_observed=root_end,
                root_stop_received_at=stop_at,
                ready_to_exit=last_stop > max(last_worker_stop, activity) and not active,
                last_assistant_message=last_message)


class NativeInputObserver:
    """Observe native automatic messages, which do not emit UserPromptSubmit."""

    def __init__(self, profile):
        self.profile = Path(profile) if profile is not None else None
        self.offsets, self.buffers, self.latest = {}, {}, None

    def pending(self, state):
        session = state.get("session_id")
        if self.profile is None or not session:
            return False
        for path in (self.profile / "projects").glob(f"*/{session}.jsonl"):
            if path.is_symlink() or not path.is_file():
                raise ValueError("Native root transcript must be a regular file")
            offset = self.offsets.get(path, 0)
            if path.stat().st_size < offset:
                raise RuntimeError("Native root transcript was truncated")
            with path.open("rb") as stream:
                stream.seek(offset)
                data = stream.read()
                self.offsets[path] = stream.tell()
            lines = (self.buffers.get(path, b"") + data).split(b"\n")
            self.buffers[path] = lines.pop()
            for line in lines:
                try:
                    event = json.loads(line)
                    if event.get("type") == "user" and not event.get("isSidechain"):
                        stamp = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
                        self.latest = max(self.latest, stamp) if self.latest is not None else stamp
                except (ValueError, KeyError, TypeError):
                    continue
        stop_at = state.get("root_stop_received_at")
        return self.latest is not None and (stop_at is None or self.latest > datetime.fromisoformat(stop_at))


def startup_response(text, handled):
    # Only installation/theme and trust for the caller's disposable workspace.
    # Never approve a tool-permission, login-method or billing dialog here.
    rules = (("theme", ("Choose the text style", "Choose the terminal theme"), b"2\r"),
             ("security_notice", ("Security notes:",), b"\r"),
             ("workspace_trust", ("Do you trust the files in this folder", "Quick safety check:"), b"y\r"),
             ("environment_key", ("Do you want to use this API key", "Use this API key?"), b"y\r"))
    for name, markers, response in rules:
        if name not in handled and any(marker in text for marker in markers):
            return name, response
    return None


def team_configs(profile):
    base, configs = Path(profile).resolve(), []
    for path in (base / "teams").glob("*/config.json"):
        try:
            if (path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(base)
                    and path.stat().st_size < 1000000):
                configs.append(dict(path=str(path), data=json.loads(path.read_text())))
        except (OSError, ValueError):
            # Native state is mutable here; a read racing its replacement is not a CLI failure.
            continue
    return configs


def run_terminal(*, argv, version, environment, prompt, workspace, output, timeout,
                 observer, execute=False, command_prefix=(), version_prefix=(),
                 cli_workspace=None, startup_only=False, native_profile=None, completion_file=None):
    positive(timeout, "timeout")
    workspace, output, observer = Path(workspace).resolve(strict=True), Path(output).resolve(), Path(observer).resolve()
    if not workspace.is_dir() or output.is_relative_to(workspace) or workspace.is_relative_to(output):
        raise ValueError("Workspace must exist and must not overlap output")
    completion = workspace / completion_file if completion_file is not None else None
    if completion is not None:
        if not completion.resolve().is_relative_to(workspace) or ".." in Path(completion_file).parts:
            raise ValueError("Completion file must be within the workspace")
        if execute and completion.exists():
            raise FileExistsError("Refusing a preexisting completion file")
    prompt = prompt.strip()
    if not prompt and not startup_only:
        raise ValueError("Prompt must not be empty")
    digest = hashlib.sha256(prompt.encode()).hexdigest()
    task_name = ".cli-request-" + digest[:16] + ".md"
    initial = f"Read {Path(cli_workspace or workspace) / task_name} and carry out the complete request in that file."
    plan = dict(backend="claude-code-agent-team", expected_version=version, argv=argv,
                command_prefix=list(command_prefix), version_prefix=list(version_prefix),
                workspace=str(workspace), output=str(output), observer=str(observer),
                timeout_seconds=timeout, environment_overrides=environment,
                prompt_characters=len(prompt), prompt_utf8_bytes=len(prompt.encode()), prompt_sha256=digest,
                transport="interactive controlling terminal; no -p", task_file=task_name,
                completion_file=str(completion) if completion is not None else None,
                status="planned", model_calls_started=False, adapter_retries=0, startup_only=startup_only)
    if not execute:
        return plan
    utility = shutil.which("script")
    if os.name != "posix" or utility is None:
        raise RuntimeError("Interactive transport requires POSIX util-linux script")
    output.mkdir(parents=True, exist_ok=False)
    observer.mkdir(parents=True, exist_ok=True)
    events = observer / "events.jsonl"
    if events.exists():
        raise FileExistsError("Refusing to reuse native observer events")
    write_json(output / "launch.json", plan)
    (output / "prompt.txt").write_text(prompt)
    if not startup_only:
        task_file = workspace / task_name
        with task_file.open("x") as stream:
            stream.write(prompt)
    report = dict(backend="claude-code-agent-team", status="preflight_error", returncode=None,
                  transport=plan["transport"], usage=None, cost_usd=None,
                  correctness="not_evaluated", model_calls_started=False, startup_actions=[])
    process, started, sent_exit, last_event_count, last_event_time = None, time.monotonic(), False, 0, time.monotonic()
    env = dict(os.environ, **environment, TERM="xterm-256color", COLUMNS="140", LINES="40")
    try:
        verified = verify_cli(argv[0], version, r"^(\d+\.\d+\.\d+) \(Claude Code\)\s*$",
                              env, workspace, version_prefix)
        write_json(output / "cli-version.json", verified)
        native = [*command_prefix, verified["executable"], *argv[1:]]
        if not startup_only:
            native.extend(["--", initial])
        # script owns terminal setup in C, avoiding Python preexec_fn in batch threads.
        command = [utility, "--quiet", "--return", "--flush", "--command", shlex.join(native), "/dev/null"]
        handled, event_size, state, config_digest = set(), -1, lifecycle_state(events), None
        native_inputs = NativeInputObserver(native_profile)
        with (output / "stdout.log").open("xb") as stdout, (output / "stderr.log").open("xb") as stderr:
            process = subprocess.Popen(command, cwd=workspace, env=env, stdin=subprocess.PIPE,
                                       stdout=stdout, stderr=stderr, start_new_session=True)
            report.update(status="running", model_calls_started=False if startup_only else None)
            try:
                while process.poll() is None:
                    if time.monotonic() - started > timeout:
                        report["status"] = "timed_out"
                        break
                    size = events.stat().st_size if events.exists() else 0
                    if size != event_size:
                        if event_size > size:
                            raise RuntimeError("Native observer evidence was truncated")
                        state, event_size = lifecycle_state(events), size
                        if native_profile is not None:
                            configs = team_configs(native_profile)
                            value = hashlib.sha256(json.dumps(configs, sort_keys=True).encode()).hexdigest()
                            if value != config_digest:
                                with (output / "native-team-history.jsonl").open("a") as stream:
                                    stream.write(json.dumps(dict(observer_event_count=state["events"], configs=configs)) + "\n")
                                config_digest = value
                    if state["events"] != last_event_count:
                        last_event_count, last_event_time = state["events"], time.monotonic()
                    state["pending_native_input"] = native_inputs.pending(state)
                    complete = completion is None or (completion.is_file() and not completion.is_symlink()
                                                      and completion.stat().st_size > 0)
                    if not sent_exit and ((startup_only and state["session_id"]) or
                            (complete and state["ready_to_exit"] and not state["pending_native_input"]
                             and time.monotonic() - last_event_time >= 2)):
                        report["native_before_exit"] = state
                        write_json(output / "native-lifecycle-before-exit.json", state)
                        if native_profile is not None:
                            write_json(output / "native-team-before-exit.json", team_configs(native_profile))
                        process.stdin.write(b"/exit\r")
                        process.stdin.flush()
                        sent_exit = True
                        report["exit_requested_after_native_stop"] = not startup_only
                        report["completion_file_observed"] = completion is not None and complete
                    path = output / "stdout.log"
                    with path.open("rb") as stream:
                        stream.seek(max(0, path.stat().st_size - 40000))
                        raw = stream.read().decode(errors="replace")
                    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", raw)
                    response = startup_response(text, handled)
                    if response is not None and not sent_exit and state["session_id"] is None:
                        name, packet = response
                        process.stdin.write(packet)
                        process.stdin.flush()
                        handled.add(name)
                        report["startup_actions"].append(name)
                    time.sleep(0.2)
                else:
                    report["status"] = "cli_exited" if process.returncode == 0 else "cli_error"
            finally:
                stop_process_group(process)
                process.stdin.close()
                report["returncode"] = process.returncode
        report["native_lifecycle"] = lifecycle_state(events)
        if report["status"] == "cli_exited" and not report["native_lifecycle"]["root_session_end_observed"]:
            report["status"] = "cli_protocol_error"
        if report["status"] == "cli_exited" and completion is not None and not report.get("completion_file_observed"):
            report["status"] = "cli_incomplete"
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
