"""Adapters for externally installed agent CLIs, not an agent runtime."""

from .claude_code_subagents import ClaudeCodeSubagentsCLI
from .claude_code_single_agent import ClaudeCodeSingleAgentCLI
from .codex_single_agent import CodexSingleAgentCLI
from .codex_subagents import CodexSubagentsCLI

__all__ = ["ClaudeCodeSubagentsCLI", "ClaudeCodeSingleAgentCLI",
           "CodexSingleAgentCLI", "CodexSubagentsCLI"]
