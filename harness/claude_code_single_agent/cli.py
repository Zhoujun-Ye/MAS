"""Native print-mode Claude with delegation tools removed and denied."""

from dataclasses import dataclass

from .._claude_cli import command, run_print
from .._claude_hooks import BLOCKED_TOOLS, SINGLE_TOOLS


@dataclass(frozen=True)
class ClaudeCodeSingleAgentCLI:
    executable: str = "claude"

    def command(self, model, *, allowed_tools=(), disallowed_tools=(), settings=None,
                isolated_settings=True, max_budget_usd=None):
        if not isolated_settings:
            raise ValueError("Strict Single requires isolated native settings and empty MCP configuration")
        if isinstance(disallowed_tools, str):
            raise ValueError("Tools must be a sequence of names")
        native = dict(settings or {}, disableAllHooks=False)
        argv = command(self.executable, model, allowed_tools=allowed_tools,
            disallowed_tools=tuple(dict.fromkeys((*BLOCKED_TOOLS, *disallowed_tools))), settings=native,
            isolated_settings=True, max_budget_usd=max_budget_usd)
        return [*argv, "--tools", ",".join(SINGLE_TOOLS), "--disable-slash-commands"]

    def run(self, prompt, *, model, workspace, output, timeout=3600, allowed_tools=(),
            disallowed_tools=(), max_budget_usd=None, settings=None, isolated_settings=True,
            execute=False, command_prefix=(), observer_dir=None, observer_target=None,
            hook_script=None, hook_python="python3"):
        return run_print(self, prompt, backend="claude-code-single-agent", model=model, workspace=workspace,
            output=output, timeout=timeout, allowed_tools=allowed_tools, disallowed_tools=disallowed_tools,
            max_budget_usd=max_budget_usd, settings=settings, isolated_settings=isolated_settings,
            execute=execute, command_prefix=command_prefix, observer_dir=observer_dir,
            observer_target=observer_target, hook_script=hook_script, hook_python=hook_python, single_agent=True)
