"""Explicit 24-attempt benchmark matrix; bounded independent CLI processes, no retries."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

from benchmarks._io import write_json
from benchmarks.dataclawbench.tasks import load_tasks as dc_tasks
from benchmarks.hybriddeepresearch.tasks import load_tasks as hdr_tasks
from benchmarks.kramabench.tasks import load_tasks as krama_tasks
from benchmarks.kramabench.semantic_judge import judge_once
from scripts.common import runtime
from scripts.common.proof import validate_runtime
from benchmarks._external import digest
from scripts.common.timeouts import TIMEOUT_SECONDS_BY_BENCHMARK, default_timeout, timeout_policy

BACKENDS = ("claude-code-single-agent", "claude-code-subagents", "codex-single-agent", "codex-subagents")


def selections(root):
    dc = [t for t in dc_tasks(root / "dataclawbench/upstream") if not t.web][:2]
    hdr = hdr_tasks(root / "hybriddeepresearch/release/hybrid_ds_release/hybrid_ds_release.jsonl")
    hdr = [next(t for t in hdr if t.category == category) for category in ("search_to_sql", "sql_to_search")]
    krama, _ = krama_tasks(root / "kramabench/upstream")
    easy = [t for t in krama if "-easy-" in t.id]
    krama = easy if len(easy) >= 2 else krama
    return [("dataclawbench", t) for t in dc] + [("hybriddeepresearch", t) for t in hdr] + [("kramabench", t) for t in krama[:2]]


def solver_command(args, benchmark, task, backend, output, *, execute=False):
    command = [sys.executable, "-m", "scripts." + benchmark + ".run", "--upstream", str(args.root / benchmark / "upstream"),
               "--backend", backend, "--task-id", task.id, "--image", args.image, "--output", str(output),
               "--credentials", str(args.credentials), "--timeout", str(default_timeout(benchmark)),
               "--offline-proof", str(args.proofs / backend / "proof.json")]
    if backend.startswith("codex-"):
        command.append("--codex-docker-isolated")
    if benchmark == "kramabench":
        command += ["--concurrency", "1", "--replay-timeout", "180", "--judge-limit", "0"]
        if execute:
            command.append("--from-plan")
    else:
        data = args.root / ("dataclawbench/upstream/assets/database" if benchmark == "dataclawbench" else "hybriddeepresearch/data")
        command += ["--data", str(data), "--authorized-attempts", "1"]
        if benchmark == "hybriddeepresearch":
            command += ["--tasks", str(args.root / "hybriddeepresearch/release/hybrid_ds_release/hybrid_ds_release.jsonl"),
                        "--web-search", "deepseek", "--max-web-requests", "4"]
    if execute:
        command.append("--execute")
    return command


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--proofs", type=Path, required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--credentials", type=Path, default=Path("/home/zhoujunye/MAS-information/.env"))
    parser.add_argument("--concurrency", type=int, default=8, choices=range(1, 9))
    parser.add_argument("--judge-concurrency", type=int, default=2, choices=range(1, 3))
    parser.add_argument("--authorized-attempts", type=int)
    parser.add_argument("--authorized-judges", type=int, default=0)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    args.root, args.output, args.proofs = args.root.resolve(), args.output.resolve(), args.proofs.resolve()
    selected = selections(args.root)
    jobs = [(bench, task, backend, args.output / "solvers" / bench / task.id / backend)
            for bench, task in selected for backend in BACKENDS]
    authorization = dict(attempts=len(jobs), maximum_judge_calls=20, retries=0,
        timeout_seconds_by_benchmark=dict(TIMEOUT_SECONDS_BY_BENCHMARK),
        timeout_policy_by_benchmark={b: timeout_policy(b) for b in TIMEOUT_SECONDS_BY_BENCHMARK},
        solver_concurrency=args.concurrency, judge_concurrency=args.judge_concurrency,
        monetary_cap=None, selections=[dict(benchmark=b, task_id=t.id, backend=k) for b, t, k, _ in jobs])
    if not args.execute:
        print(json.dumps(authorization, indent=2))
        return 0
    if len(jobs) != 24 or args.authorized_attempts != 24 or args.authorized_judges not in (0, 20):
        raise ValueError("Require exactly 24 authorized solvers and zero or at most 20 authorized judges")
    os.umask(0o077)
    args.output.mkdir(parents=True, exist_ok=False)
    write_json(args.output / "authorization.json", {**authorization, "authorized_judges": args.authorized_judges})
    args.image = json.loads(subprocess.check_output(["docker", "image", "inspect", args.image], text=True))[0]["Id"]
    for backend in BACKENDS:
        proof = json.loads((args.proofs / backend / "proof.json").read_text())
        codex = backend.startswith("codex-")
        catalog = runtime.CODEX_CATALOG.with_name("deepseek-single-models.json") if backend.endswith("single-agent") else runtime.CODEX_CATALOG
        validate_runtime(proof, backend, image_id=args.image,
            binary_sha256=digest(runtime.CODEX if codex else runtime.CLAUDE),
            catalog_sha256=digest(catalog) if codex else None)
    active, lock, stop = set(), threading.Lock(), threading.Event()

    def command_run(command, log):
        if stop.is_set():
            return None
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.with_suffix(".stdout.log").open("x") as stdout, log.with_suffix(".stderr.log").open("x") as stderr:
            # Never inherit credential-like host variables into CLI subprocesses.
            env = {name: os.environ[name] for name in ("PATH", "HOME", "LANG") if name in os.environ}
            with lock:
                if stop.is_set():
                    return None
                process = subprocess.Popen(command, stdout=stdout, stderr=stderr, env=env)
                active.add(process)
            try:
                deadline = time.monotonic() + max(TIMEOUT_SECONDS_BY_BENCHMARK.values()) + 600
                while True:
                    try:
                        return process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        if not stop.is_set() and time.monotonic() < deadline:
                            continue
                        stop.set()
                        process.terminate()
                        try:
                            return process.wait(timeout=20)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            return process.wait(timeout=10)
            finally:
                with lock:
                    active.discard(process)

    def interrupt(signum, frame):
        stop.set()
        with lock:
            for process in active:
                process.terminate()

    previous = {s: signal.signal(s, interrupt) for s in (signal.SIGTERM, signal.SIGINT)}
    def checked(function, *values):
        try:
            return function(*values)
        except BaseException:
            interrupt(None, None)
            raise
    rows = []
    before = after = None
    try:
        # All offline preflights must pass before any paid attempt starts.
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futures = [pool.submit(checked, command_run, solver_command(args, b, t, k, out),
                                   args.output / "logs" / (b + "-" + t.id + "-" + k + "-preflight")) for b, t, k, out in jobs]
            if any(f.result() != 0 for f in futures):
                raise RuntimeError("Matrix preflight failed; no paid attempts dispatched")
        key = runtime.credential(args.credentials)
        before = runtime.safe_balance(key, args.output, "balance-before")
        if before is None or not before.get("response", {}).get("is_available"):
            raise RuntimeError("Balance preflight failed; no paid attempts dispatched")

        def solve(job):
            b, t, k, out = job
            code = command_run(solver_command(args, b, t, k, out, execute=True),
                               args.output / "logs" / (b + "-" + t.id + "-" + k + "-solver"))
            report = out / t.id / k / "report.json"
            row = dict(benchmark=b, task_id=t.id, backend=k, returncode=code, run=str(out), status="not_started")
            if report.exists():
                record = json.loads(report.read_text())
                row["status"] = record["status"]
                if record.get("fatal_provider_error"):
                    stop.set()
            return row

        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            for future in as_completed([pool.submit(checked, solve, job) for job in jobs]):
                rows.append(future.result())
                write_json(args.output / "progress.json", dict(stage="solvers", rows=rows))
                print(json.dumps(rows[-1]), flush=True)

        def score(job):
            b, t, k, out = job
            target = args.output / "grades" / b / t.id / k
            result = dict(benchmark=b, task_id=t.id, backend=k, judge_calls=0)
            if stop.is_set():
                return {**result, "status": "not_started"}
            if b == "kramabench":
                summary = out / "summary.json"
                if not summary.exists():
                    return {**result, "status": "missing_summary"}
                record = json.loads(summary.read_text())["rows"][0]
                result.update(status=record.get("grade", {}).get("status"), grade=record.get("grade"),
                              pipeline_exit_code=record.get("pipeline_exit_code"),
                              pipeline_answer_matches_submission=record.get("pipeline_answer_matches_submission"))
                if record.get("status") == "cli_exited" and result["status"] == "pending_judge" and args.authorized_judges:
                    judged = judge_once(upstream=args.root / b / "upstream", task_id=t.id, backend=k,
                        submission_path=out / t.id / k / "submission.json", question=t.query, key=key, output=target)
                    result.update(status=judged["status"], grade=judged.get("grade"), judge_calls=judged["attempted_calls"])
                return result
            predicted = out / "predictions.jsonl"
            if not predicted.exists():
                return {**result, "status": "missing_predictions"}
            predictions = [json.loads(line) for line in predicted.read_text().splitlines() if line.strip()]
            text_judge = b == "dataclawbench" or t.category != "search_to_sql"
            calls = sum(bool(p["final_answer"].strip()) for p in predictions) if text_judge and args.authorized_judges else 0
            command = [sys.executable, "-m", "scripts." + b + ".score", "--run", str(out),
                       "--upstream", str(args.root / b / "upstream"), "--output", str(target)]
            if b == "hybriddeepresearch":
                command += ["--tasks", str(args.root / "hybriddeepresearch/release/hybrid_ds_release/hybrid_ds_release.jsonl"),
                            "--db-root", str(args.root / "hybriddeepresearch/data")]
                if not text_judge:
                    command.append("--execute-sql")
            if calls:
                command += ["--execute-judges", "--judge-limit", str(calls), "--judge-model", "deepseek-flash",
                            "--credentials", str(args.credentials), "--judge-base-url", "https://api.deepseek.com"]
            code = command_run(command, args.output / "logs" / (b + "-" + t.id + "-" + k + "-grade"))
            receipt = json.loads((target / "receipt.json").read_text()) if (target / "receipt.json").exists() else {}
            return {**result, "status": "completed" if code == 0 else "grading_failed", "returncode": code,
                    "judge_calls": receipt.get("judge_calls"), "output": str(target)}

        grades = []
        with ThreadPoolExecutor(max_workers=args.judge_concurrency) as pool:
            for future in as_completed([pool.submit(checked, score, job) for job in jobs]):
                grades.append(future.result())
                write_json(args.output / "grading-progress.json", dict(rows=grades))
        after = runtime.safe_balance(key, args.output, "balance-after")
        write_json(args.output / "summary.json", dict(rows=rows, grades=grades, authorization=authorization,
            account_delta=runtime.balance_deltas(before, after) if before and after else None,
            accounting_scope="Whole shared-account interval, not attributable per-condition charges",
            interrupted=stop.is_set(), finished_at=runtime.now()))
        grades_ok = all(g["status"] not in {"missing_summary", "missing_predictions", "grading_failed", "judge_error", "not_started"} for g in grades)
        return 0 if len(rows) == 24 and all(r["status"] == "cli_exited" for r in rows) and grades_ok and not stop.is_set() else 1
    except BaseException as error:
        interrupt(None, None)
        write_json(args.output / "failure.json", dict(error_type=type(error).__name__,
            completed_solver_receipts=len(rows), balance_preflight_passed=before is not None,
            interrupted=stop.is_set(), observed_at=runtime.now()))
        raise
    finally:
        if stop.is_set():
            for receipt in args.output.glob("solvers/**/container-ownership.json"):
                owned = json.loads(receipt.read_text())
                name = owned.get("container_name", "")
                if name.startswith("mas-cli6-"):
                    subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=20)
        for s, handler in previous.items():
            signal.signal(s, handler)


if __name__ == "__main__":
    raise SystemExit(main())
