"""Codex with native multi-agent features enabled; scheduling stays native."""

from dataclasses import dataclass
from .. import _codex_cli


@dataclass(frozen=True)
class CodexSubagentsCLI:
    executable: str = "codex"

    def command(self, model, **options):
        return _codex_cli.command(self.executable, model, subagents=True, **options)

    def run(self, prompt, **options):
        return _codex_cli.run(self, prompt, subagents=True, **options)
