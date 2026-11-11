"""Minimal delegation prompt for the explicitly selected Native study condition."""

PROMPT = """Use Claude Code's native subagents as an orchestrator-worker team. You are the lead agent: analyze the task, plan how to answer it, delegate parts of the work to subagents with the native Agent tool, and synthesize their results into the final answer.

Always deploy at least one subagent."""
