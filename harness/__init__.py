"""Adapters for externally installed agent CLIs, not an agent runtime."""

from .claude_code_subagents import ClaudeCodeSubagentsCLI
from .claude_code_single_agent import ClaudeCodeSingleAgentCLI

__all__ = ["ClaudeCodeSubagentsCLI", "ClaudeCodeSingleAgentCLI"]
