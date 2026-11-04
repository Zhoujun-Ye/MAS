"""Plan/freeze one native CLI benchmark condition; execute only when authorized."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from benchmarks._io import fingerprint, write_json
from benchmarks.kramabench.evaluation import scoring_contract
from benchmarks.kramabench.semantic_judge import judge_once
from benchmarks.kramabench.tasks import load_tasks
from scripts.kramabench import cli_runtime as runtime
from scripts.kramabench.cli_runtime import compact
from scripts.common import runtime as shared
from scripts.common.runtime import monitor, safe_balance
from analysis.native_evidence import native_single_agent, native_subagents
from scripts.common.proof import validate_runtime
from analysis.codex_evidence import inspect as codex_evidence



def admission(root, report):
    folder = root / report["task_id"] / report["backend"]
    result = dict(passed=False, status=report["status"], reference_accessed=False)
    try:
        runtime.submission(folder / "workspace")
        result["valid_submission"] = True
    except (OSError, ValueError, TypeError) as error:
        result["artifact_error"] = str(error)
    if report["backend"].startswith("codex-"):
        result["native_codex"] = codex_evidence(folder / "native-profile/codex", single=report["backend"].endswith("single-agent"))
        native_ok = result["native_codex"]["passed"]
    elif report["backend"] == "claude-code-single-agent":
        result["native_single_agent"] = native_single_agent(folder)
        native_ok = result["native_single_agent"]["passed"]
    elif report["backend"] == "claude-code-subagents":
        result["native_subagents"] = native_subagents(folder)
        native_ok = result["native_subagents"]["passed"]
    else:
        raise ValueError("Unsupported backend: " + report["backend"])
    result["passed"] = bool(report["status"] == "cli_exited" and result.get("valid_submission") and native_ok)
    return result


def validate_native_proof(args, plan, *, frozen=False):
    raw = args.offline_proof.read_bytes()
    proof_digest = hashlib.sha256(raw).hexdigest()
    if frozen and plan.get("offline_proof_sha256") != proof_digest:
        raise ValueError("Offline proof changed after freeze")
    proof = json.loads(raw)
    offline_ok = proof.get("paid_calls") == 0 and proof.get("network") == "none"
    codex = args.backend.startswith("codex-")
    binary = plan["cli_binaries"]["codex" if codex else "claude"]
    catalog = plan.get("model_catalogs", {}).get(args.backend)
    validate_runtime(proof, args.backend, image_id=plan["image_id"],
                     binary_sha256=binary["sha256"],
                     catalog_sha256=catalog["sha256"] if catalog else None)
    if not offline_ok:
        raise ValueError("Missing successful offline native guard/transport proof")
    return proof_digest


def freeze(args):
    tasks, plan = runtime.preflight(args)
    if not 1 <= len(tasks) <= 104 or plan["attempts"] != len(tasks):
        raise ValueError("Expected one attempt per selected task")
    proof_digest = validate_native_proof(args, plan)
    plan.update(kind="native_cli_benchmark", backend=args.backend,
                offline_proof_sha256=proof_digest,
                admission_task=tasks[0].id,
                evaluation="Versioned answer metrics and separate no-network replay; no extra pipeline judge")
    write_json(args.output / "plan.json", plan)
    write_json(args.output / "preflight-ok.json", dict(paid_calls=0, plan_sha256=fingerprint(plan)))
    return tasks, plan


def validate(args):
    plan = json.loads((args.output / "plan.json").read_text())
    if fingerprint(plan) != json.loads((args.output / "preflight-ok.json").read_text())["plan_sha256"]:
        raise ValueError("Plan receipt changed")
    validate_native_proof(args, plan, frozen=True)
    tasks, _ = load_tasks(args.upstream)
    selected = tasks if args.all_tasks else [next(t for t in tasks if t.id == i) for i in args.selected_task_ids]
    if (plan["kind"] != "native_cli_benchmark" or plan["backend"] != args.backend or [asdict(t) for t in selected] != plan["tasks"]
            or plan.get("organization_override") != getattr(args, "organization_override", None)
            or plan["backend_instructions"] != {b: shared.condition_instructions(args, b) for b in args.backends}
            or plan["backend_options"] != {b: runtime.backend_options(args, b) for b in args.backends}
            or shared.source_manifest() != plan["source"]
            or fingerprint(runtime.verify_inputs(args.upstream)) != plan["inputs_sha256"]
            or scoring_contract(args.upstream) != plan["scoring"]):
        raise ValueError("Frozen condition/source/data/scoring changed")
    for value in plan["cli_binaries"].values():
        if hashlib.sha256(Path(value["path"]).read_bytes()).hexdigest() != value["sha256"]:
            raise ValueError("CLI changed after freeze")
    for value in plan.get("model_catalogs", {}).values():
        if hashlib.sha256(Path(value["path"]).read_bytes()).hexdigest() != value["sha256"]:
            raise ValueError("Model catalog changed after freeze")
    if (args.concurrency, args.timeout, args.judge_limit, args.replay_timeout) != (
            plan["concurrency"], plan["timeout_seconds"], plan["judge_limit"], plan["replay_timeout_seconds"]):
        raise ValueError("Frozen settings changed")
    args.image = plan["image_id"]
    return selected, plan


def execute(args, tasks, plan):
    os.umask(0o077)
    with (args.output / "execution-start.json").open("x") as stream:
        json.dump(dict(started_at=shared.now(), authorized_attempts=len(tasks),
            authorized_judge_calls=args.judge_limit, retries=0, monetary_cap=None), stream)
    key = shared.credential(args.credentials)
    before = safe_balance(key, args.output, "balance-before-solvers")
    if before is None or not before.get("response", {}).get("is_available"):
        raise RuntimeError("Balance preflight unavailable; no calls dispatched")
    stop, done, lock, active, reports = threading.Event(), threading.Event(), threading.Lock(), set(), []
    watcher = threading.Thread(target=monitor, args=(args.output, stop, active, lock, done), daemon=True)
    watcher.start()
    def interrupt(signum, frame):
        stop.set()
        with lock:
            identities = list(active)
        for identity in identities:
            subprocess.run(["docker", "stop", "--time", "1", identity], capture_output=True)
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGINT, interrupt)
    def record(value):
        reports.append(value)
        write_json(args.output / "progress.json", dict(stage="solving", finished=len(reports), expected=len(tasks),
                                                     rows=[compact(r) for r in reports], observed_at=shared.now()))
        print(json.dumps(compact(value)), flush=True)
    backend = args.backends[0]
    try:
        canary = next(t for t in tasks if t.id == plan["admission_task"])
        record(runtime.run_attempt(canary, backend, args, key, stop, active, lock))
        audit = admission(args.output, reports[0])
        write_json(args.output / "admission-audit.json", audit)
        if audit["passed"] and not stop.is_set():
            with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
                futures = [pool.submit(runtime.run_attempt, task, backend, args, key, stop, active, lock)
                           for task in tasks if task.id != canary.id]
                for future in as_completed(futures):
                    record(future.result())
        else:
            write_json(args.output / "admission-stopped.json", dict(not_admitted=len(tasks)-1, no_replacements=True))
    finally:
        stop.set()
        done.set()
        watcher.join(timeout=5)
        after = safe_balance(key, args.output, "balance-after-solvers")
        billing = dict(balance_delta_by_currency=shared.balance_deltas(before, after) if after else None,
                       scope="Account-wide solver interval, possibly including other account use")
        write_json(args.output / "solver-billing.json", billing)
        write_json(args.output / "solver-results.json", dict(rows=reports, plan_sha256=fingerprint(plan)))
    write_json(args.output / "progress.json", dict(stage="offline_evaluation", finished=len(reports), expected=len(tasks)))
    with ThreadPoolExecutor(max_workers=min(args.concurrency, 6)) as pool:
        rows = list(pool.map(lambda r: runtime.collect_attempt(args.output / r["task_id"] / backend, r, args), reports))
    write_json(args.output / "summary-base.json", dict(plan=plan, rows=rows, billing=billing, paid_judge_calls=0))
    pending = [r for r in rows if r.get("grade", {}).get("status") == "pending_judge"]
    judgments = []
    judge_before = safe_balance(key, args.output, "balance-before-judges") if pending and args.judge_limit else None
    if judge_before is not None:
        for report in pending[:args.judge_limit]:
            task = next(t for t in tasks if t.id == report["task_id"])
            folder = args.output / task.id / backend
            value = judge_once(upstream=args.upstream, task_id=task.id, backend=backend,
                submission_path=folder / "submission.json", question=task.query, key=key, output=folder / "semantic-judge")
            judgments.append(value)
            report["semantic_judge"] = value
            if value["status"] == "graded":
                report["effective_grade"] = value["grade"]
            if value.get("fatal"):
                break
    judge_after = safe_balance(key, args.output, "balance-after-judges") if judge_before else None
    judge_bill = dict(attempted_calls=len(judgments), balance_delta_by_currency=(
        shared.balance_deltas(judge_before, judge_after) if judge_before and judge_after else None))
    write_json(args.output / "judge-billing.json", judge_bill)
    write_json(args.output / "summary.json", dict(plan=plan, rows=rows, billing=billing,
        judge_billing=judge_bill, paid_judge_calls=len(judgments), finished_at=shared.now()))
    write_json(args.output / "progress.json", dict(stage="finished", finished=len(rows), expected=len(tasks),
                                                 judge_calls=len(judgments), observed_at=shared.now()))
    if len(rows) != len(tasks):
        raise RuntimeError("Admission failed; no replacement runs dispatched")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("claude-code-subagents", "claude-code-single-agent",
                                             "codex-single-agent", "codex-subagents"), required=True)
    parser.add_argument("--codex-docker-isolated", action="store_true")
    parser.add_argument("--task-id", action="append", default=[])
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--offline-proof", type=Path, required=True)
    parser.add_argument("--organization-prompt", type=Path,
                        help="Explicit Subagents study instruction override; frozen with its SHA-256")
    parser.add_argument("--credentials", type=Path, default=Path("/home/zhoujunye/MAS-information/.env"))
    parser.add_argument("--image", default="mas-information/kramabench:20261101-v1")
    parser.add_argument("--concurrency", type=int, default=12)
    parser.add_argument("--timeout", type=int, default=3600)
    parser.add_argument("--replay-timeout", type=int, default=600)
    parser.add_argument("--judge-limit", type=int, choices=range(11), default=0)
    parser.add_argument("--from-plan", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.concurrency <= 12 or args.timeout <= 0 or args.replay_timeout <= 0:
        parser.error("Expected 1-12 CLIs and positive timeouts")
    args.upstream, args.output = args.upstream.resolve(), args.output.resolve()
    args.organization_override = shared.organization_override(args.organization_prompt, args.backend)
    tasks, _ = load_tasks(args.upstream)
    if len(args.task_id) != len(set(args.task_id)) or set(args.task_id) - {t.id for t in tasks}:
        parser.error("Task IDs must be unique members of the pinned workload")
    args.strict_single = args.backend.endswith("single-agent")
    args.backends = (args.backend,)
    args.all_tasks = not args.task_id
    args.selected_task_ids = args.task_id
    tasks, plan = validate(args) if args.from_plan else freeze(args)
    if args.execute:
        execute(args, tasks, plan)
    else:
        print(json.dumps(dict(status="frozen_preflight", attempts=len(tasks), judge_limit=args.judge_limit)))


if __name__ == "__main__":
    main()
