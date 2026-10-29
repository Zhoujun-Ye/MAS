"""Run BrowseComp-Plus questions under conditions C0-C5 (paid model calls).

Phase 0 check, five questions per condition:
  .venv/bin/python scripts/run_bcp.py --out outputs/bcp-phase0 --limit 5
C5 replays the sub-tasks of C1 from the same output directory; C1 runs first.
Rerunning the same command resumes: finished runs are kept, errors rerun.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mas_info.bcp.data import load_tasks
from mas_info.bcp.prompts import frozen_prompts
from mas_info.bcp.retriever import BM25, Truncator
from mas_info.bcp.system import solve
from mas_info.bcp.tools import get_document_tool, search_tool
from mas_info.config import ROOT, load_config, load_env, resolve
from mas_info.llm import ChatClient, ModelConfig
from mas_info.runner import RunSpec, prepare_output, result_path, run_batch
from mas_info.trace import read_trace


def select(tasks: list[dict], args) -> list[dict]:
    if args.ids:
        wanted = set(args.ids)
        tasks = [task for task in tasks if task["query_id"] in wanted]
    if args.sample:
        tasks = random.Random(args.seed).sample(tasks, args.sample)
    return tasks[: args.limit] if args.limit else tasks


def c1_subtasks(out: Path, spec: RunSpec) -> list[str]:
    """Tasks the C1 lead dispatched for the same question and repeat, in order."""
    c1 = RunSpec(spec.benchmark, spec.task_id, "C1", spec.repeat)
    path = result_path(out, c1)
    if not path.exists() or json.loads(path.read_text())["status"] == "error":
        raise RuntimeError(f"C5 needs a finished C1 run: {c1.run_id}")
    events = read_trace(out / "traces" / f"{c1.run_id}.jsonl")
    return [e["task"] for e in events if e["type"] == "boundary_msg" and e["direction"] == "down"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=ROOT / "configs/bcp.yaml")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--conditions", nargs="+", default=["C0", "C1", "C2", "C3", "C4"])
    parser.add_argument("--ids", nargs="+", help="query ids to run")
    parser.add_argument("--sample", type=int, help="random sample size (with --seed)")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--limit", type=int, help="first N selected questions")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--concurrency", type=int)
    args = parser.parse_args()

    load_env()
    cfg = load_config(ROOT / "configs/base.yaml", args.config)
    retriever_cfg, budget = cfg["retriever"], cfg["budget"]
    settings = {"k": retriever_cfg["k"], "snippet_max_tokens": retriever_cfg["snippet_max_tokens"], **budget}
    tasks = select(load_tasks(resolve(cfg["tasks"])), args)
    by_id = {task["query_id"]: task for task in tasks}

    truncate = Truncator(retriever_cfg["snippet_max_tokens"], resolve(retriever_cfg["tokenizer"]))
    prompts = frozen_prompts(settings)
    frozen = {
        "benchmark": "bcp",
        "agent_model": cfg["agent_model"],
        "retriever": retriever_cfg,
        "budget": budget,
        "prompts": prompts,
    }
    prepare_output(
        args.out,
        frozen,
        {
            "prompt_chars": {c: {role: len(text) for role, text in p.items()} for c, p in prompts.items()},
            "snippet_truncation": truncate.kind,
        },
    )

    retriever = BM25(retriever_cfg["index"], retriever_cfg.get("java_home"))
    tools = [search_tool(retriever, retriever_cfg["k"], truncate), get_document_tool(retriever)]
    client = ChatClient(ModelConfig(**cfg["agent_model"]))

    def execute(spec: RunSpec, trace) -> dict:
        subtasks = None
        if spec.condition == "C5":
            subtasks = c1_subtasks(args.out, spec)
            if not subtasks:
                return {"status": "not_applicable", "reason": "the C1 lead dispatched no task"}
        return solve(
            by_id[spec.task_id],
            spec.condition,
            client=client,
            search_tools=tools,
            trace=trace,
            settings=settings,
            subtasks=subtasks,
        )

    specs = [
        RunSpec("bcp", task["query_id"], condition, repeat)
        for condition in args.conditions
        for task in tasks
        for repeat in range(args.repeats)
    ]
    concurrency = args.concurrency or cfg["concurrency"]
    statuses = run_batch([s for s in specs if s.condition != "C5"], execute, args.out, concurrency)
    later = [s for s in specs if s.condition == "C5"]
    if later:
        for status, count in run_batch(later, execute, args.out, concurrency).items():
            statuses[status] = statuses.get(status, 0) + count
    print(json.dumps(statuses))


if __name__ == "__main__":
    main()
