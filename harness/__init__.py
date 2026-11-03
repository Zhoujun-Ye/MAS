"""Adapters for externally installed agent CLIs, not an agent runtime."""

from .claude_code_agent_team import ClaudeCodeAgentTeamCLI
from .claude_code_subagents import ClaudeCodeSubagentsCLI
from .claude_code_single_agent import ClaudeCodeSingleAgentCLI
from .deepagents import DeepAgentsCLI

__all__ = ["ClaudeCodeAgentTeamCLI", "ClaudeCodeSubagentsCLI", "ClaudeCodeSingleAgentCLI", "DeepAgentsCLI"]
