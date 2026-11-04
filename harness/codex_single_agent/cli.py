"""Codex with native multi-agent features disabled."""

from dataclasses import dataclass
from .. import _codex_cli


@dataclass(frozen=True)
class CodexSingleAgentCLI:
    executable: str = "codex"

    def command(self, model, **options):
        return _codex_cli.command(self.executable, model, subagents=False, **options)

    def run(self, prompt, **options):
        return _codex_cli.run(self, prompt, subagents=False, **options)
