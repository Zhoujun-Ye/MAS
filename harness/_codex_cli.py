"""Pinned native Codex transport using DeepSeek's Responses endpoint."""

import json
from pathlib import Path

from ._cli import run_cli

VERSION = "0.159.3"


def command(executable, model, *, subagents, base_url="https://api.deepseek.com", model_catalog=None,
            docker_isolated=False):
    settings = {
        "model_provider": "deepseek",
        "model_providers.deepseek.name": "DeepSeek",
        "model_providers.deepseek.base_url": base_url,
        "model_providers.deepseek.env_key": "DEEPSEEK_API_KEY",
        "model_providers.deepseek.wire_api": "responses",
        "model_providers.deepseek.request_max_retries": 0,
        "model_providers.deepseek.stream_max_retries": 0,
        "features.multi_agent": subagents,
        "features.multi_agent_v2": subagents,
        "features.in_app_updates": False,
        "features.enable_request_compression": False,
        "web_search": "disabled",
        "approval_policy": "never",
        "model_reasoning_effort": "max",
    }
    if model_catalog:
        settings["model_catalog_json"] = str(model_catalog)
    argv = [executable, "exec", "--ignore-user-config", "--ignore-rules",
            "--skip-git-repo-check", "--json", "--color", "never",
            "--sandbox", "danger-full-access" if docker_isolated else "workspace-write", "--model", model]
    for key, value in settings.items():
        argv += ["-c", key + "=" + json.dumps(value)]
    return [*argv, "-"]


def parse_result(path):
    rows = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    completed = [r for r in rows if r.get("type") == "turn.completed"]
    failed = any(r.get("type") in {"turn.failed", "error"} for r in rows)
    return dict(status="cli_exited" if completed and not failed else "incomplete",
                usage=completed[-1].get("usage") if completed else None,
                accounting_scope="native root turn; child usage coverage unverified",
                delegation_verified=False, correctness="not_evaluated")


def run(adapter, prompt, *, subagents, model, workspace, output, timeout=900,
        execute=False, base_url="https://api.deepseek.com", command_prefix=(),
        profile=None, profile_target=None, model_catalog=None, docker_isolated=False):
    if docker_isolated and tuple(command_prefix[:2]) != ("docker", "exec"):
        raise ValueError("Inner sandbox opt-out requires explicit Docker exec transport")
    output = Path(output).resolve()
    home = Path(profile) if profile is not None else output / "native-profile"
    if execute:
        work = Path(workspace).resolve(strict=True)
        if output.is_relative_to(work) or work.is_relative_to(output):
            raise ValueError("Workspace and output must not overlap")
        output.mkdir(parents=True, exist_ok=False, mode=0o700)
        home.mkdir(mode=0o700, exist_ok=profile is not None)
    if command_prefix and profile_target:
        command_prefix = (*command_prefix, "env", "CODEX_HOME=" + profile_target)
    return run_cli(backend="codex-subagents" if subagents else "codex-single-agent",
                   argv=command(adapter.executable, model, subagents=subagents, base_url=base_url,
                                model_catalog=model_catalog, docker_isolated=docker_isolated),
                   version=VERSION, version_pattern=r"^codex-cli (\S+)",
                   environment={"CODEX_HOME": str(home)}, prompt=prompt,
                   workspace=workspace, output=output / "cli", timeout=timeout, execute=execute,
                   parse_result=parse_result, command_prefix=command_prefix)
