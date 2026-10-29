"""Run τ²-bench tasks under conditions C0-C4 with τ²'s own orchestrator and evaluator (paid).

Phase 0 check, five telecom tasks per condition, one trial:
  .venv/bin/python scripts/run_tau2.py --out outputs/tau2-phase0 --domain telecom --limit 5 --trials 1
Rerunning the same command resumes: finished runs are kept, errors rerun.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loguru import logger

from mas_info.config import ROOT, load_config, load_env
from mas_info.llm import ChatClient, ModelConfig
from mas_info.runner import RunSpec, prepare_output, run_batch
from mas_info.tau.prompts import frozen_prompts
from mas_info.tau.run import load_tasks, register, solve


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=ROOT / "configs/tau2.yaml")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--domain", default="telecom")
    parser.add_argument("--conditions", nargs="+", default=["C0", "C1", "C2", "C3", "C4"])
    parser.add_argument("--ids", nargs="+", help="task ids to run")
    parser.add_argument("--limit", type=int, help="first N tasks of the split")
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--concurrency", type=int)
    parser.add_argument("--log-level", default="WARNING", help="τ² (loguru) log level")
    args = parser.parse_args()
    if "C5" in args.conditions:
        parser.error("C5 is defined for BrowseComp-Plus only")

    logger.remove()
    logger.add(sys.stderr, level=args.log_level)
    load_env()
    cfg = load_config(ROOT / "configs/base.yaml", args.config)
    register()
    tasks = load_tasks(args.domain, cfg["domains"][args.domain])
    if args.ids:
        tasks = [task for task in tasks if task.id in set(args.ids)]
    tasks = tasks[: args.limit] if args.limit else tasks
    by_id = {task.id: task for task in tasks}

    frozen = {
        "benchmark": f"tau2-{args.domain}",
        "split": cfg["domains"][args.domain],
        "agent_model": cfg["agent_model"],
        "user_model": cfg["user_model"],
        "communicate_scoring": cfg["communicate_scoring"],
        "budget": cfg["budget"],
        "max_steps": cfg["max_steps"],
        "max_errors": cfg["max_errors"],
        "seed": cfg["seed"],
        "prompts": frozen_prompts(),
    }
    prepare_output(args.out, frozen)
    client = ChatClient(ModelConfig(**cfg["agent_model"]))

    def execute(spec: RunSpec, trace) -> dict:
        task = by_id[spec.task_id]
        result = solve(spec, trace, task=task, domain=args.domain, settings=cfg, client=client, sims=args.out / "sims")
        criteria = task.evaluation_criteria
        actions = criteria.actions if criteria is not None and criteria.actions else []
        return {**result, "gold_actions": [action.model_dump(mode="json") for action in actions]}

    specs = [
        RunSpec(args.domain, task.id, condition, trial)
        for condition in args.conditions
        for task in tasks
        for trial in range(args.trials)
    ]
    statuses = run_batch(specs, execute, args.out, args.concurrency or cfg["concurrency"])
    print(json.dumps(statuses))


if __name__ == "__main__":
    main()
