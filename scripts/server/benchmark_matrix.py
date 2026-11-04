"""Explicit matched Claude benchmark matrix; independent processes, no retries."""

import argparse
import hashlib
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

BACKENDS = ("claude-code-single-agent", "claude-code-subagents",)
BENCHMARKS = ("dataclawbench", "hybriddeepresearch", "kramabench")


def task_fingerprint(benchmark, task):
    public = dict(benchmark=benchmark, id=task.id,
                  question=getattr(task, "question", getattr(task, "query", None)),
                  source_sha256=getattr(task, "source_sha256", None))
    return hashlib.sha256(json.dumps(public, sort_keys=True).encode()).hexdigest()


def manifest_selections(root, manifest, offset, count):
    if manifest.get("kind") != "validation20-v1" or offset < 0 or offset + count > 20:
        raise ValueError("Invalid validation manifest or task slice")
    pools = dict(dataclawbench=dc_tasks(root / "dataclawbench/upstream"),
                 hybriddeepresearch=hdr_tasks(root / "hybriddeepresearch/release/hybrid_ds_release/hybrid_ds_release.jsonl"),
                 kramabench=krama_tasks(root / "kramabench/upstream")[0])
    result = []
    for benchmark in BENCHMARKS:
        frozen = manifest["benchmarks"][benchmark]
        ids = [row["task_id"] for row in frozen]
        if len(ids) != 20 or len(set(ids)) != 20:
            raise ValueError("Each validation benchmark must contain 20 unique IDs")
        by_id = {t.id: t for t in pools[benchmark]}
        for row in frozen:
            task = by_id.get(row["task_id"])
            if task is None or task_fingerprint(benchmark, task) != row["task_sha256"]:
                raise ValueError("Frozen validation task changed or disappeared")
        result.extend((benchmark, by_id[i]) for i in ids[offset:offset + count])
    return result


def balanced_sample(tasks, count, group, seed):
    """Round-robin public strata with stable seeded ordering, never inspect gold."""
    groups = {}
    for task in tasks:
        groups.setdefault(group(task), []).append(task)
    if len(tasks) < count:
        raise ValueError("Not enough tasks for the requested sample")
    def rank(value):
        return hashlib.sha256(f"{seed}:{value}".encode()).hexdigest()
    names = sorted(groups, key=rank)
    for values in groups.values():
        values.sort(key=lambda task: rank(task.id))
    selected = []
    while len(selected) < count:
        for name in names:
            if groups[name] and len(selected) < count:
                selected.append(groups[name].pop(0))
    return selected


def selections(root, count=2, seed=42):
    if count != 2:
        krama, _ = krama_tasks(root / "kramabench/upstream")
        pools = (
            ("dataclawbench", dc_tasks(root / "dataclawbench/upstream"), lambda t: t.category),
            ("hybriddeepresearch", hdr_tasks(root / "hybriddeepresearch/release/hybrid_ds_release/hybrid_ds_release.jsonl"), lambda t: t.category),
            ("kramabench", krama, lambda t: t.domain),
        )
        return [(bench, task) for bench, tasks, group in pools
                for task in balanced_sample(tasks, count, group, seed)]
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
    command += ["--effort", getattr(args, "effort", "max")]
    if backend == "claude-code-subagents" and getattr(args, "organization_prompt", None):
        command += ["--organization-prompt", str(args.organization_prompt)]
    if benchmark == "kramabench":
        command += ["--concurrency", "1", "--replay-timeout", "180", "--judge-limit", "0"]
        if execute:
            command.append("--from-plan")
    else:
        data = args.root / ("dataclawbench/upstream/assets/database" if benchmark == "dataclawbench" else "hybriddeepresearch/data")
        command += ["--data", str(data), "--authorized-attempts", "1"]
        if getattr(task, "web", benchmark == "hybriddeepresearch"):
            command += ["--web-search", "deepseek", "--max-web-requests", "4"]
        if benchmark == "hybriddeepresearch":
            command += ["--tasks", str(args.root / "hybriddeepresearch/release/hybrid_ds_release/hybrid_ds_release.jsonl"),
                        ]
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
    parser.add_argument("--concurrency", type=int, default=8, choices=range(1, 13))
    parser.add_argument("--effort", choices=("high", "max"), default="max")
    parser.add_argument("--organization-prompt", type=Path)
    parser.add_argument("--tasks-per-benchmark", type=int, default=2, choices=range(1, 101))
    parser.add_argument("--sample-seed", type=int, default=42)
    parser.add_argument("--task-manifest", type=Path, help="Frozen public ID/hash manifest, never questions or gold")
    parser.add_argument("--task-offset", type=int, default=0)
    parser.add_argument("--judge-concurrency", type=int, default=2, choices=range(1, 3))
    parser.add_argument("--authorized-attempts", type=int)
    parser.add_argument("--authorized-judges", type=int, default=0)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    args.root, args.output, args.proofs = args.root.resolve(), args.output.resolve(), args.proofs.resolve()
    manifest = json.loads(args.task_manifest.read_text()) if args.task_manifest else None
    if args.task_offset and manifest is None:
        raise ValueError("A task offset requires a frozen task manifest")
    selected = (manifest_selections(args.root, manifest, args.task_offset, args.tasks_per_benchmark)
                if manifest else selections(args.root) if args.tasks_per_benchmark == 2
                else selections(args.root, args.tasks_per_benchmark, args.sample_seed))
    jobs = [(bench, task, backend, args.output / "solvers" / bench / task.id / backend)
            for bench, task in selected for backend in BACKENDS]
    maximum_judges = sum(1 for b, t, _, _ in jobs
                         if b != "hybriddeepresearch" or t.category != "search_to_sql")
    authorization = dict(attempts=len(jobs), maximum_judge_calls=maximum_judges, retries=0, effort=args.effort,
        tasks_per_benchmark=args.tasks_per_benchmark, sample_seed=args.sample_seed,
        selection_policy="frozen-validation-manifest" if manifest else "legacy-two" if args.tasks_per_benchmark == 2 else "seeded-public-strata-round-robin",
        task_offset=args.task_offset,
        task_manifest_sha256=digest(args.task_manifest) if args.task_manifest else None,
        organization_override=runtime.organization_override(args.organization_prompt, "claude-code-subagents"),
        timeout_seconds_by_benchmark=dict(TIMEOUT_SECONDS_BY_BENCHMARK),
        timeout_policy_by_benchmark={b: timeout_policy(b) for b in TIMEOUT_SECONDS_BY_BENCHMARK},
        solver_concurrency=args.concurrency, judge_concurrency=args.judge_concurrency,
        monetary_cap=None, selections=[dict(benchmark=b, task_id=t.id, backend=k) for b, t, k, _ in jobs])
    if not args.execute:
        print(json.dumps(authorization, indent=2))
        return 0
    if len(jobs) != 6 * args.tasks_per_benchmark or args.authorized_attempts != len(jobs) or args.authorized_judges not in (0, maximum_judges):
        raise ValueError(f"Require exactly {len(jobs)} authorized solvers and zero or at most {maximum_judges} authorized judges")
    if manifest:
        expected = manifest["baseline_settings"]
        observed = dict(effort=args.effort, organization_sha256={k: hashlib.sha256(runtime.backend_instructions(k).encode()).hexdigest() for k in BACKENDS},
                        timeout_seconds_by_benchmark=dict(TIMEOUT_SECONDS_BY_BENCHMARK),
                        solver_concurrency=args.concurrency, judge_concurrency=args.judge_concurrency)
        if expected != observed or args.organization_prompt:
            raise ValueError("Baseline settings differ from the frozen validation study")
    os.umask(0o077)
    args.output.mkdir(parents=True, exist_ok=False)
    write_json(args.output / "authorization.json", {**authorization, "authorized_judges": args.authorized_judges})
    if manifest:
        write_json(args.output / "task-manifest.json", manifest)
    args.image = json.loads(subprocess.check_output(["docker", "image", "inspect", args.image], text=True))[0]["Id"]
    for backend in BACKENDS:
        proof = json.loads((args.proofs / backend / "proof.json").read_text())
        validate_runtime(proof, backend, image_id=args.image,
            binary_sha256=digest(runtime.CLAUDE))
        if args.effort != "max" and not (proof.get("requested_effort") == args.effort
                and proof.get("request_effort_verified") is True):
            raise ValueError("Matching offline request-effort proof is required for this study")
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
        return 0 if len(rows) == len(jobs) and all(r["status"] == "cli_exited" for r in rows) and grades_ok and not stop.is_set() else 1
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
