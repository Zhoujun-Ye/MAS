"""Interactive native Claude Code Agent Teams, never print-mode subagents."""

from dataclasses import dataclass
from pathlib import Path

from .._claude_cli import VERSION, command, environment, hook_settings
from .terminal import run_terminal


@dataclass(frozen=True)
class ClaudeCodeAgentTeamCLI:
    executable: str = "claude"

    def command(self, model, **options):
        return command(self.executable, model, teams=True, **options)

    def run(self, prompt, *, model, workspace, output, timeout=3600,
            allowed_tools=(), max_budget_usd=None, execute=False, command_prefix=(),
            disallowed_tools=(), settings=None, isolated_settings=False,
            version_prefix=None, observer_dir=None, observer_target=None, hook_script=None,
            hook_python="python3", cli_workspace=None, startup_only=False, native_profile=None,
            completion_file=None):
        observer = Path(observer_dir or Path(output)/"observer")
        native_settings = dict(settings or {})
        native_settings["hooks"] = hook_settings(observer_target or observer,
            hook_script or Path(__file__).parents[1]/"_claude_hooks.py", hook_python)
        return run_terminal(argv=self.command(model, allowed_tools=allowed_tools,
            max_budget_usd=max_budget_usd, disallowed_tools=disallowed_tools,
            settings=native_settings, isolated_settings=isolated_settings),
            version=VERSION, environment=environment(True), prompt=prompt, workspace=workspace,
            output=output, timeout=timeout, execute=execute, observer=observer,
            command_prefix=command_prefix,
            version_prefix=command_prefix if version_prefix is None else version_prefix,
            cli_workspace=cli_workspace, startup_only=startup_only, native_profile=native_profile,
            completion_file=completion_file)
