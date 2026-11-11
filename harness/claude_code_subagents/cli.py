"""Print-mode Claude CLI with native subagents and Agent Teams disabled."""

from dataclasses import dataclass

from .._claude_cli import command, run_print
from .._claude_hooks import SUBAGENT_TOOLS


@dataclass(frozen=True)
class ClaudeCodeSubagentsCLI:
    executable: str = "claude"

    def command(self, model, **options):
        return [*command(self.executable, model, **options),
                "--tools", ",".join(SUBAGENT_TOOLS), "--disable-slash-commands"]

    def run(self, prompt, *, model, workspace, output, timeout=3600, allowed_tools=(),
            disallowed_tools=(), max_budget_usd=None, settings=None, isolated_settings=False,
            execute=False, command_prefix=(), observer_dir=None, observer_target=None,
            hook_script=None, hook_python="python3"):
        return run_print(self, prompt, backend="claude-code-subagents", model=model, workspace=workspace,
            output=output, timeout=timeout, allowed_tools=allowed_tools, disallowed_tools=disallowed_tools,
            max_budget_usd=max_budget_usd, settings=settings, isolated_settings=isolated_settings,
            execute=execute, command_prefix=command_prefix, observer_dir=observer_dir,
            observer_target=observer_target, hook_script=hook_script, hook_python=hook_python)
