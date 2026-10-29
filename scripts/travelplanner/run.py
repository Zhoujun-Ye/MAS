#!/usr/bin/env python3
"""Authorized six-task/four-form pilot; no judge, simulator or expansion."""
import argparse
from dataclasses import asdict
import hashlib
import json
import signal
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from benchmarks.travelplanner.adapter import NativeSession, ROOT as BENCH, tasks, public_task, team_for, OUTPUT, FIELDS
from harness.agent_team import AgentTeam
from harness.config import load_config, load_env, source_digest, digest
from harness.llm import ChatClient, ModelConfig
from harness.pool import bind_permissions
from harness.runner import RunSpec, prepare_output, record_balance, run_batch
from harness.trace import read_trace, validate

TASK_IDS = ("validation-1", "validation-2", "validation-60", "validation-61", "validation-120", "validation-121")
FORMS = ("summary", "structured", "document_retrieval", "adaptive")
LIMITS = dict(tool_budget=30, max_calls=48, max_messages=24, max_reads=12, max_input_chars=800_000)


def valid_final(text):
    try:
        plan = json.loads(text)
        return isinstance(plan, list) and len(plan) == 3 and all(
            isinstance(day, dict) and type(day.get("day")) is int and day["day"] == i + 1
            and all(isinstance(day.get(k), str) for k in FIELDS) for i, day in enumerate(plan))
    except (ValueError, TypeError):
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--authorized-24-runs", action="store_true", required=True)
    args = parser.parse_args()
    config = load_config(ROOT / "configs/base.yaml")
    cfg = ModelConfig(**config["agent_model"])
    selected = {t["task_id"]: t for t in tasks() if t["task_id"] in TASK_IDS}
    assert len(selected) == 6
    plans = {k: team_for(public_task(v)) for k, v in selected.items()}
    # Rotated condition order; do not always award the last arm the warm cache.
    specs = [RunSpec("travelplanner", task, form, 0) for i, task in enumerate(TASK_IDS)
             for form in FORMS[i % len(FORMS):] + FORMS[:i % len(FORMS)]]
    frozen = dict(task_ids=TASK_IDS, plans={k: v.payload() for k, v in plans.items()},
                  model=asdict(cfg), limits=LIMITS, pricing=config["pricing"],
                  source=source_digest(), driver=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  prepared=digest(json.loads((BENCH / "assets/prepared.json").read_text())),
                  concurrency=3, specs=[asdict(s) for s in specs],
                  scope="24 paired runs; Full Context excluded by user; no paid judge or expansion; no monetary ceiling",
                  split="held-out pilot from official validation, NOT official test split")
    prepare_output(args.output, frozen)
    load_env()
    stopping = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stopping.set())

    def execute(spec, trace):
        if stopping.is_set():
            return dict(status="skipped", reason="user_interrupted")
        row, plan = selected[spec.task_id], plans[spec.task_id]
        with NativeSession() as native:
            client = ChatClient(cfg)
            try:
                tools = native.tools()
                permissions = bind_permissions(plan, {t.name: "search" for t in tools})
                team = AgentTeam(plan, spec.condition, client, trace, tools, permissions,
                                 final_validator=valid_final, final_contract=OUTPUT,
                                 should_stop=stopping.is_set, **LIMITS)
                result = team.run_task(public_task(row))
                if native.errors:
                    raise RuntimeError("Native environment errors: " + str(native.errors))
                if result["status"] == "completed":
                    result["grade"] = native.grade(row, result["final"])
                    result["correct"] = result["grade"].get("audited_correct", result["grade"]["correct"])
                    result["success"] = result["correct"]
                result["semantic_loss"] = None
                return result
            finally:
                client._http.close()

    record_balance(args.output, cfg, "start")
    try:
        statuses = run_batch(specs, execute, args.output, 3, config["pricing"])
        print(json.dumps(statuses), flush=True)
        for path in sorted((args.output / "traces").glob("*.jsonl")):
            problems = validate(read_trace(path))
            if problems:
                print(json.dumps(dict(trace=path.name, integrity_errors=problems)), flush=True)
    finally:
        record_balance(args.output, cfg, "end")


if __name__ == "__main__":
    main()
