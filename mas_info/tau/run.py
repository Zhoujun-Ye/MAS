"""One τ²-bench simulation under one condition.

τ² builds the environment and user simulator, runs its orchestrator and scores
the result with its own evaluator; only the agent side is ours.
"""

from __future__ import annotations

from pathlib import Path

from ..llm import ChatClient
from ..runner import RunSpec
from ..trace import Trace
from .team import CONTEXTS, TeamContext, create_team_agent

AGENT_NAME = "mas_team"


def register() -> None:
    from tau2.registry import registry

    if AGENT_NAME not in registry.get_agents():
        registry.register_agent_factory(create_team_agent, AGENT_NAME)


def load_tasks(domain: str, split: str) -> list:
    from tau2.runner.helpers import get_tasks

    return get_tasks(domain, task_split_name=split)


def solve(
    spec: RunSpec,
    trace: Trace,
    *,
    task,
    domain: str,
    settings: dict,
    client: ChatClient,
    sims: Path,
) -> dict:
    from tau2 import TextRunConfig
    from tau2.data_model.semantic_communication import CommunicateScoring
    from tau2.runner import build_text_orchestrator, run_simulation

    budget = settings["budget"]
    CONTEXTS[spec.run_id] = TeamContext(
        spec.condition,
        client,
        trace,
        tool_calls=budget["tool_calls"],
        max_turns=budget["max_turns"],
        max_delegations=budget["max_delegations"],
    )
    try:
        config = TextRunConfig(
            domain=domain,
            agent=AGENT_NAME,
            llm_agent=client.cfg.model,
            llm_args_agent={"mas_run": spec.run_id},
            llm_user=settings["user_model"]["model"],
            llm_args_user=settings["user_model"]["args"],
            communicate_scoring=CommunicateScoring(scorer=settings["communicate_scoring"]),
            max_steps=settings["max_steps"],
            max_errors=settings["max_errors"],
            seed=settings["seed"],
        )
        orchestrator = build_text_orchestrator(
            config, task, seed=settings["seed"] + spec.repeat, simulation_id=spec.run_id
        )
        simulation = run_simulation(orchestrator)
    finally:
        CONTEXTS.pop(spec.run_id, None)
    sims.mkdir(parents=True, exist_ok=True)
    (sims / f"{spec.run_id}.json").write_text(simulation.model_dump_json(indent=2), encoding="utf-8")
    info = simulation.reward_info
    reward = info.reward if info is not None else None
    reason = getattr(simulation.termination_reason, "value", simulation.termination_reason)
    front = orchestrator.agent.front
    trace.emit(
        "final",
        agent=front.name,
        reward=reward,
        termination_reason=reason,
        context_tokens=front.last_prompt_tokens,
    )
    db_check = info.db_check if info is not None else None
    return {
        "status": "completed",
        "reward": reward,
        "success": reward is not None and reward >= 1.0 - 1e-6,
        "db_match": db_check.db_match if db_check is not None else None,
        "termination_reason": reason,
        "reward_info": info.model_dump(mode="json") if info is not None else None,
        "delegations": orchestrator.agent.delegations,
        "tool_budget_used": orchestrator.agent.budget.used,
    }
