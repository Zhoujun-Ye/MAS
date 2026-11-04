"""Bounded four-attempt provisioning smoke; separate from baseline study defaults."""

import argparse
from decimal import Decimal
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from benchmarks._io import write_json
from benchmarks.dataclawbench.tasks import load_tasks as dc_tasks
from benchmarks.hybriddeepresearch.tasks import load_tasks as hdr_tasks
from scripts.common import runtime


def cny(receipt):
    rows = receipt["response"]["balance_infos"]
    return Decimal(next(row["total_balance"] for row in rows if row["currency"] == "CNY"))


def stop_owned(output, process):
    for path in output.glob("*/*/report.json"):
        row = json.loads(path.read_text())
        if row.get("container_id"):
            subprocess.run(["docker", "stop", "--time", "1", row["container_id"]], capture_output=True)
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--proofs", type=Path, required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--authorized-attempts", type=int, required=True)
    parser.add_argument("--adapted-prompt-pilot", action="store_true")
    budget = parser.add_mutually_exclusive_group(required=True)
    budget.add_argument("--budget-cny", type=Decimal)
    budget.add_argument("--no-monetary-limit", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.authorized_attempts != 4 or (not args.no_monetary_limit and args.budget_cny != Decimal("10")):
        raise ValueError("Authorize four attempts and either CNY 10 or no monetary limit")
    limited = not args.no_monetary_limit
    dc_root = args.root / "dataclawbench/upstream"
    hdr_root = args.root / "hybriddeepresearch/upstream"
    release = args.root / "hybriddeepresearch/release/hybrid_ds_release/hybrid_ds_release.jsonl"
    dc = next(t for t in dc_tasks(dc_root) if not t.web)
    hdr = next(t for t in hdr_tasks(release) if t.category == "search_to_sql")
    conditions = [(task, mode) for task in (dc, hdr) for mode in ("single-agent", "subagents")]
    if args.adapted_prompt_pilot:
        if limited:
            raise ValueError("Adapted prompt pilot was authorized without a monetary limit")
        text_task = next(t for t in hdr_tasks(release) if t.category == "sql_to_search")
        conditions = [(dc, "subagents"), (hdr, "subagents"),
                      (text_task, "single-agent"), (text_task, "subagents")]
    authorization = dict(attempts=4, budget_cny=str(args.budget_cny) if limited else None, retries=0, judge_calls=0,
        native_budget_usd_per_attempt=1.0 if limited else None, timeout_seconds_per_attempt=300,
        max_web_requests_per_hdr_attempt=4, web_search="deepseek", model="deepseek-flash[1m]",
        selections=[dict(benchmark=t.benchmark, task_id=t.id, backend="claude-code-"+m) for t,m in conditions],
        early_account_stop_cny="2.00" if limited else None, reserve_cny="8.00" if limited else None,
        limitation="Native cost uses fallback pricing, not DeepSeek invoices; account monitoring is delayed, not a hard provider-side cap.")
    if not args.execute:
        print(json.dumps(authorization, indent=2))
        return
    os.umask(0o077)
    args.output.mkdir(parents=True, exist_ok=False)
    write_json(args.output / "authorization.json", authorization)
    key = runtime.credential(args.credentials)
    initial = runtime.balance(key)
    if not initial["response"].get("is_available") or (limited and cny(initial) < args.budget_cny):
        raise ValueError("Insufficient available balance for authorized scope")
    write_json(args.output / "balance-before.json", initial)
    code = Path(__file__).resolve().parents[2]
    results = []
    for task, mode in conditions:
        current = runtime.balance(key)
        if limited and cny(initial) - cny(current) >= Decimal("2"):
            break
        backend = "claude-code-" + mode
        output = args.output / (task.benchmark + "-" + mode + ("-" + task.id if args.adapted_prompt_pilot else ""))
        command = [sys.executable, str(code / "scripts" / task.benchmark / "run.py"),
            "--upstream", str(dc_root if task.benchmark == "dataclawbench" else hdr_root),
            "--data", str(dc_root / "assets/database" if task.benchmark == "dataclawbench" else args.root / "hybriddeepresearch/data"),
            "--backend", backend, "--task-id", task.id, "--image", args.image,
            "--output", str(output), "--credentials", str(args.credentials), "--authorized-attempts", "1",
            "--offline-proof", str(args.proofs / task.benchmark / backend / "proof.json"),
            "--max-web-requests", "4", "--timeout", "300", "--execute"]
        if limited:
            command += ["--max-budget-usd", "1"]
        if task.web:
            command += ["--tasks", str(release), "--web-search", "deepseek"]
        stop_reason = None
        with (args.output / (output.name + ".stdout.log")).open("x") as stdout, (args.output / (output.name + ".stderr.log")).open("x") as stderr:
            process = subprocess.Popen(command, stdout=stdout, stderr=stderr, start_new_session=True)
            try:
                deadline = time.monotonic() + 420
                while process.poll() is None:
                    if time.monotonic() >= deadline:
                        stop_reason = "smoke_wall_time_limit"
                    else:
                        try:
                            current = runtime.balance(key)
                            write_json(args.output / "balance-latest.json", current)
                            if limited and cny(initial) - cny(current) >= Decimal("2"):
                                stop_reason = "early_account_budget_stop"
                        except Exception:
                            stop_reason = "balance_monitor_unavailable"
                    if stop_reason:
                        stop_owned(output, process)
                        break
                    time.sleep(3)
            finally:
                if process.poll() is None:
                    stop_owned(output, process)
        after = runtime.balance(key)
        write_json(args.output / (output.name + "-balance-after.json"), after)
        row = dict(benchmark=task.benchmark, backend=backend, task_id=task.id,
                   returncode=process.returncode, stop_reason=stop_reason,
                   cumulative_account_spend_cny=str(cny(initial)-cny(after)), run=str(output))
        results.append(row)
        write_json(args.output / "smoke-results.json", dict(rows=results, solver_attempts_started=len(results), judge_calls=0))
        print(json.dumps(row), flush=True)
        if stop_reason or process.returncode:
            break
    final = runtime.balance(key)
    write_json(args.output / "balance-after.json", final)
    write_json(args.output / "summary.json", dict(rows=results, solver_attempts_started=len(results),
        expected_attempts=4, judge_calls=0, account_spend_cny=str(cny(initial)-cny(final)),
        all_conditions_completed=len(results)==4 and all(r["returncode"]==0 for r in results),
        accounting_scope="DeepSeek solver and web account interval; earlier Tavily credit recorded separately; not a per-task invoice"))


if __name__ == "__main__":
    main()
