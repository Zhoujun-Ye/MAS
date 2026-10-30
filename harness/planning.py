"""Condition-blind Leader decomposition, frozen once before team execution."""
import json
from pathlib import Path

from .accounting import estimate
from .agent import Agent
from .communication import parse_payload
from .config import digest
from .llm import ChatClient
from .pool import Member, POOL, TeamSpec
from .runner import write_json
from .trace import Trace, read_trace, usage_summary

SELECTOR = "leader-decomposition-isolated-v1"
PLAN_SYSTEM = POOL["leader"].system + """
Planning phase only: use the complete public request and fixed capability/tool
catalogue, not domain retrieval, hidden answers or communication-condition results.
Select 2 or 3 complementary workers plus leader. Assign concrete subtasks,
required outputs, completion criteria and which findings must reach which peers.
Describe dependencies inside the assignments. The leader coordinates and
synthesizes only; assign every domain lookup or verification to an eligible worker.
Do not solve the task, guess facts, invent roles or modify tool permissions.
Every worker receives the complete public request. Avoid redundant copies of
the same work. Return only JSON with exactly this schema:
{"members":[{"role":"existing_role","assignment":"specific work"}, ...]}.
Include leader exactly once. No tools, Markdown or extra fields.
"""


def planning_input(request, tool_capabilities):
    catalogue = {
        name: dict(responsibility=role.responsibility,
                   tools=sorted(tool for tool, capability in tool_capabilities.items()
                                if capability in role.capabilities))
        for name, role in POOL.items()
    }
    return json.dumps(dict(request=request, roles=catalogue), ensure_ascii=False)


def parse_plan(request, text):
    value = parse_payload(text)
    if not isinstance(value, dict) or set(value) != {"members"} or not isinstance(value["members"], list):
        raise ValueError("Invalid plan shape")
    members = value["members"]
    if not 3 <= len(members) <= 4 or any(
        not isinstance(m, dict) or set(m) != {"role", "assignment"}
        or not all(isinstance(v, str) for v in m.values()) for m in members
    ):
        raise ValueError("Plan must contain leader and 2-3 fixed workers")
    return TeamSpec(digest(request), tuple(Member(**m) for m in members), selector=SELECTOR)


def plan_team(request, client, trace, tool_capabilities):
    """One tool-less planning call. Invalid plans fail, never silently replan an arm."""
    agent = Agent("leader_planner", client, trace, PLAN_SYSTEM, usage_role="planning")
    agent.append(dict(role="user", content=planning_input(request, tool_capabilities)))
    reply = agent.call(tool_choice="none")
    if reply.finish_reason == "length" or reply.message.get("tool_calls"):
        agent.refuse(reply.message.get("tool_calls") or [])
        raise ValueError("Invalid or truncated plan; no automatic planning repair")
    plan = parse_plan(request, reply.message.get("content") or "")
    trace.emit("final", agent=agent.name, content=reply.message["content"])
    return plan


def frozen_plan(task_id, request, cfg, directory, stopping, pricing, tool_capabilities):
    """Persist planning usage and immutable decomposition independently of any adapter."""
    task_id = str(task_id)
    if not task_id or task_id in (".", "..") or "/" in task_id or "\\" in task_id:
        raise ValueError("Task ID must be a single filename component")
    directory = Path(directory)
    path = directory / f"{task_id}.json"
    control = digest(dict(request=request, model=vars(cfg), system=PLAN_SYSTEM,
                          catalogue=planning_input(request, tool_capabilities), selector=SELECTOR))
    if path.exists():
        record = json.loads(path.read_text())
        if record.get("planning_digest") != control:
            raise ValueError("Saved planning configuration changed; use a new output directory")
        plan = TeamSpec(record["plan"]["task_digest"], tuple(Member(**m) for m in record["plan"]["members"]),
                        record["plan"]["selector"])
        plan.validate_task(request)
        if plan.selector != SELECTOR or record["plan_digest"] != plan.digest:
            raise ValueError("Saved plan digest or selector mismatch")
        # Apply the same structural checks on resume as on initial generation.
        if parse_plan(request, json.dumps(dict(members=record["plan"]["members"]))) != plan:
            raise ValueError("Invalid saved plan")
        return plan
    trace_path = directory / f"{task_id}.jsonl"
    if trace_path.exists():
        raise RuntimeError("Prior planning attempt has no saved plan; no automatic extra planning calls")
    if stopping.is_set():
        raise RuntimeError("Interrupted before planning")
    client = ChatClient(cfg)
    try:
        with Trace(trace_path, f"plan_{task_id}") as trace:
            trace.emit("run_start", task_id=task_id, phase="planning", planning_digest=control)
            try:
                plan = plan_team(request, client, trace, tool_capabilities)
                trace.emit("run_end", status="completed")
            except Exception as error:
                trace.emit("error", message=str(error))
                trace.emit("run_end", status="error")
                raise
        events = read_trace(trace_path)
        write_json(path, dict(plan=plan.payload(), plan_digest=plan.digest, planning_digest=control,
                             usage=usage_summary(events), cost_usd_estimate=estimate(events, pricing)))
        return plan
    finally:
        client._http.close()
