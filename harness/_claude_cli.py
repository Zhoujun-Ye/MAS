"""Shared native Claude CLI arguments, observations and explicit permission policies."""

import json
from pathlib import Path
import shlex

from ._cli import positive, run_cli

VERSION = "2.1.286"
HOOK_EVENTS = ("SessionStart", "SessionEnd", "UserPromptSubmit", "Stop", "SubagentStart",
               "SubagentStop", "TeammateIdle", "PreToolUse", "PostToolUse", "PostToolUseFailure")


def hook_settings(target, script, python="python3", *, single_agent=False, require_delegation=False):
    if single_agent and require_delegation:
        raise ValueError('Single cannot require delegation')
    argv = [python, "-I", str(script), "--output", str(Path(target)/"events.jsonl")]
    if single_agent:
        argv.append("--single-agent")
    if require_delegation:
        argv.append('--require-delegation')
    command = shlex.join(argv)
    return {event: [{"hooks": [{"type": "command", "command": command}]}] for event in HOOK_EVENTS}


def environment():
    return {"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "0",
            "CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS": "0",
            "CLAUDE_CODE_MAX_RETRIES": "0", "DISABLE_AUTOUPDATER": "1",
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}


def command(executable, model, *, allowed_tools=(), disallowed_tools=(), settings=None,
            isolated_settings=False, max_budget_usd=None):
    if not model.strip() or model.startswith("-"):
        raise ValueError("An explicit model is required")
    native = dict(settings or {})
    native["env"] = dict(native.get("env") or {}, CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS="0")
    native.pop("teammateMode", None)
    args = [
        str(executable), "--print", "--verbose", "--output-format", "stream-json",
        "--permission-mode", "default"]
    args.extend(["--model", model, "--settings", json.dumps(native, separators=(",", ":"))])
    for flag, tools in (("--allowedTools", allowed_tools), ("--disallowedTools", disallowed_tools)):
        if tools:
            if isinstance(tools, str) or any(not t.strip() or t.startswith("-") for t in tools):
                raise ValueError("Tools must be a sequence of nonempty names")
            args.extend([flag, ",".join(tools)])
    if max_budget_usd is not None:
        positive(max_budget_usd, "max_budget_usd")
        args.extend(["--max-budget-usd", str(max_budget_usd)])
    if isolated_settings:
        args.extend(["--setting-sources", "", "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}'])
    return args


def result_event(path, *, single_agent=False):
    result = None
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except ValueError:
            return dict(status="cli_protocol_error", error="Invalid stream-json event")
        if isinstance(event, dict) and event.get("type") == "result":
            result = event
    if result is None:
        return dict(status="cli_protocol_error", error="Missing native result event")
    status = "cli_error" if result.get("is_error") or result.get("subtype") != "success" else "cli_exited"
    return dict(status=status, native_result=result, usage=result.get("usage"), cost_usd=result.get("total_cost_usd"),
                accounting_scope=("native_result; native helper usage coverage unverified" if single_agent else
                                  "native_result; subagent usage coverage unverified"))


def run_print(adapter, prompt, *, backend, model, workspace, output, timeout=3600, allowed_tools=(),
              disallowed_tools=(), max_budget_usd=None, settings=None, isolated_settings=False,
              execute=False, command_prefix=(), observer_dir=None, observer_target=None,
              hook_script=None, hook_python="python3", single_agent=False, require_delegation=False):
    observer = Path(observer_dir or Path(output)/"observer")
    native = dict(settings or {})
    native["hooks"] = hook_settings(observer_target or observer,
        hook_script or Path(__file__).with_name("_claude_hooks.py"), hook_python,
        single_agent=single_agent, require_delegation=require_delegation)
    if single_agent or require_delegation:
        native["disableAllHooks"] = False
    return run_cli(backend=backend,
        argv=adapter.command(model, allowed_tools=allowed_tools, disallowed_tools=disallowed_tools,
            max_budget_usd=max_budget_usd, settings=native, isolated_settings=isolated_settings),
        version=VERSION, version_pattern=r"^(\d+\.\d+\.\d+) \(Claude Code\)\s*$",
        environment=environment(), prompt=prompt, workspace=workspace, output=output,
        timeout=timeout, execute=execute,
        parse_result=lambda path: result_event(path, single_agent=single_agent), command_prefix=command_prefix)
