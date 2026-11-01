"""Single-context ablation of LeaderSubagent, with the exact same Agent loop."""

from .subagents import LeaderSubagent


class SingleAgent(LeaderSubagent):
    """All approved domain tools, original task and append-only local history.

    No child contexts, role catalog, delegation tool or additional model loop.
    The inherited ``leader`` field/trace ID names the sole root agent for schema
    compatibility; its usage_role is ``single``.
    """

    def __init__(self, client, trace, tools=(), *, domain_tools=None, **kwargs):
        if {"templates", "leader_tools", "allowed_tools"} & kwargs.keys():
            raise ValueError("SingleAgent grants are specified through domain_tools")
        tools = tuple(tools)
        grants = tuple(tool.name for tool in tools) if domain_tools is None else tuple(domain_tools)
        kwargs.setdefault("max_turns", kwargs.get("session_model_calls", 40))
        kwargs.setdefault("tool_budget", kwargs.get("session_tool_calls", 80))
        super().__init__(client, trace, (), tools, leader_tools=grants, allowed_tools=grants, **kwargs)
