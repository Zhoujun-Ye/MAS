"""Grade finished BrowseComp-Plus runs with the official judge prompt (paid model calls).

  .venv/bin/python scripts/grade_bcp.py --out outputs/bcp-phase0

The judge is ``judge_model`` in configs/base.yaml. Incomplete runs count as
wrong without a judge call; provider errors and unparseable judgements stay
ungraded and are retried by the next invocation.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mas_info.bcp.data import load_tasks
from mas_info.bcp.grade import grade
from mas_info.config import ROOT, load_config, load_env, resolve
from mas_info.llm import ChatClient, ModelConfig, ProviderError
from mas_info.runner import write_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=ROOT / "configs/bcp.yaml")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--concurrency", type=int, default=8)
    args = parser.parse_args()

    load_env()
    cfg = load_config(ROOT / "configs/base.yaml", args.config)
    tasks = {task["query_id"]: task for task in load_tasks(resolve(cfg["tasks"]))}
    judge = ChatClient(ModelConfig(**cfg["judge_model"]))

    def needs_grade(path: Path) -> bool:
        target = args.out / "grades" / path.name
        return not target.exists() or json.loads(target.read_text()).get("correct") is None

    results = [json.loads(p.read_text()) for p in sorted((args.out / "results").glob("*.json")) if needs_grade(p)]
    results = [r for r in results if r["status"] in ("completed", "incomplete")]

    def one(result: dict) -> str:
        task = tasks[result["task_id"]]
        if result["status"] == "incomplete":
            record = {"correct": False, "incomplete": True}
        else:
            try:
                record = grade(judge, task["query"], result["result"][0]["output"], task["answer"])
            except ProviderError as error:
                return f"{result['run_id']}: judge error {error.kind}"
        write_json(args.out / "grades" / f"{result['run_id']}.json", {"run_id": result["run_id"], **record})
        return f"{result['run_id']}: correct={record['correct']}"

    with ThreadPoolExecutor(args.concurrency) as pool:
        for line in pool.map(one, results):
            print(line, flush=True)


if __name__ == "__main__":
    main()
