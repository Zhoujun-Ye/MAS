"""Plan or explicitly execute native CLI tasks; never starts a judge or retries."""

import argparse
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tarfile
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.common.prompts.conditions import condition_instructions, organization_override
from scripts.common.prompts.limits import limit_instructions
from benchmarks._external import asset_manifest, digest, verify_sources, write_jsonl
from benchmarks.dataclawbench.tasks import load_tasks as dataclaw_tasks, REVISION as DC_REVISION
from benchmarks.hybriddeepresearch.tasks import load_tasks as hybrid_tasks, REVISION as HDR_REVISION
from harness import ClaudeCodeSingleAgentCLI, ClaudeCodeSubagentsCLI
from analysis.run_integrity import inspect_run
from harness.runtime_support import runtime
from harness.runtime_support.credential_gateway import CredentialGateway
from harness.runtime_support.proof import validate as validate_proof, validate_runtime, validate_effort
from benchmarks.policy import default_timeout, timeout_policy
from analysis.native_evidence import native_single_agent, native_subagents
from scripts.common import evidence

BACKENDS = {"claude-code-single-agent": ClaudeCodeSingleAgentCLI, "claude-code-subagents": ClaudeCodeSubagentsCLI}


def evaluable_prediction(row):
    """Outcome evaluation is separate from native-organization admission."""
    return row.get("status") == "cli_exited" or (
        row.get("status") == "native_condition_unverified"
        and row.get("cli", {}).get("status") == "cli_exited"
        and row.get("cli", {}).get("returncode") == 0)


@contextmanager
def graceful_signals():
    def interrupt(signum, frame):
        # Ignore repeated termination while the attempt unwinds its cleanup.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        raise KeyboardInterrupt

    previous = {number: signal.getsignal(number) for number in (signal.SIGTERM, signal.SIGINT)}
    try:
        for number in previous:
            signal.signal(number, interrupt)
        yield
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def load(args):
    tasks = dataclaw_tasks(args.upstream) if args.benchmark == "dataclawbench" else hybrid_tasks(args.tasks)
    ids = args.task_id
    if not ids or len(ids) != len(set(ids)) or set(ids) - {t.id for t in tasks}:
        raise ValueError("Select explicit unique --task-id values from this dataset")
    by_id = {t.id: t for t in tasks}
    return [by_id[i] for i in ids]


def run_web_limit(task, args):
    """Run-wide web request limit shared by the prompt, helper ledger and host gateway."""
    return (getattr(args, "max_web_requests", None) or 4) if task.web else 0


def instructions(task, backend, organization_override=None, *, timeout, web_limit=0, evidence_mode=None, worker=False):
    if web_limit and not task.web:
        raise ValueError("A web request limit requires a web-enabled task")
    common = "Do not install packages or seek benchmark questions, gold answers, reference SQL or solutions.\n"
    if task.benchmark == "dataclawbench":
        common += "The supplied database is read-only at /data; ./database points to it. Follow the original output guidelines.\n"
    else:
        common += (f"The read-only SQLite database is /data/{task.db}/{task.db}_template.sqlite.\n"
                   "Discover the schema yourself. A supplied *_kb.jsonl is optional domain knowledge, not a solution.\n"
                   "Use python3 /benchmark-tools.py sql --db PATH --query SQL for read-only queries.\n"
                   "Return concise text for entity/intersection questions; for a SQL question return one canonical query in a fenced sql block.\n")
    common += ("Web search/fetch are enabled: python3 /benchmark-tools.py search --query TEXT; "
               "python3 /benchmark-tools.py fetch --url URL.\n" if task.web else "No web search, fetching, or other external data access.\n")
    common += limit_instructions(timeout, web_limit)
    if worker:
        return common
    common += ('Write /workspace/submission.json with exactly {"final_answer": "your answer as text"}. '
               'If incomplete, use empty final_answer and explain in the CLI final response.\n')
    return common + condition_instructions(
        SimpleNamespace(organization_override=organization_override,evidence_mode=evidence_mode), backend)


def mounts(task, args):
    if task.benchmark == "dataclawbench":
        expected = args.upstream / "assets" / args.data_variant
        if args.data.resolve() != expected.resolve():
            raise ValueError("DataClaw inputs must be the chosen upstream assets/database or database_clear, never QA/tasks")
        return [(args.data, "/data", True)]
    folder = args.data / task.db
    database = folder / (task.db + "_template.sqlite")
    if not database.is_file() or database.is_symlink():
        raise ValueError("Missing regular SQLite database: " + str(database))
    result = [(database, f"/data/{task.db}/{database.name}", True)]
    kb = folder / (task.db + "_kb.jsonl")
    if kb.exists():
        if kb.is_symlink() or not kb.is_file():
            raise ValueError("Knowledge file must be regular")
        result.append((kb, f"/data/{task.db}/{kb.name}", True))
    return result


def plan(args, tasks):
    expected = DC_REVISION if args.benchmark == "dataclawbench" else HDR_REVISION
    revision = subprocess.check_output(["git", "-C", str(args.upstream), "rev-parse", "HEAD"], text=True).strip()
    if revision != expected:
        raise ValueError("Upstream checkout does not match the documented source pin")
    verify_sources(args.upstream, args.benchmark)
    evaluator = evaluator_manifest(args.upstream, args.benchmark)
    assets = {}
    for task in tasks:
        for source, target, _ in mounts(task, args):
            assets[str(source)] = asset_manifest(source) if source.is_dir() else digest(source)
    prompts = {t.id: t.question + "\n\n" + instructions(t, args.backend, getattr(args, "organization_override", None),
                                                         timeout=args.timeout, web_limit=run_web_limit(t, args),evidence_mode=getattr(args,'evidence_mode',None))
               for t in tasks}
    options = runtime.options(args.backend)
    if any(t.web for t in tasks) and not args.web_search:
        raise ValueError("This selection requires explicit --web-search; no silent web-free substitution")
    return dict(benchmark=args.benchmark, backend=args.backend, revision=revision,
                task_ids=[t.id for t in tasks], task_sources={t.id: t.source_sha256 for t in tasks},
                prompts={k: dict(sha256=hashlib.sha256(v.encode()).hexdigest(), characters=len(v),
                                 utf8_bytes=len(v.encode())) for k, v in prompts.items()},
                assets=assets, attempts=len(tasks), retries=0, judge_calls=0, options=options,
                image=args.image, network="none", timeout=args.timeout, timeout_policy=timeout_policy(args.benchmark, args.timeout),
                record_resources=getattr(args,'record_resources',False),
                web_search=args.web_search,
                web_request_limits={t.id: run_web_limit(t, args) for t in tasks},
                native_environment=runtime.native_env(args.backend, effort=getattr(args, "effort", "max")),
                effort=getattr(args, "effort", "max"),
                max_budget_usd=getattr(args, "max_budget_usd", None),
                max_web_requests=getattr(args, "max_web_requests", None),
                organization_prompt=condition_instructions(args, args.backend), evidence=evidence.configuration(getattr(args,'evidence_mode',None)),
                organization_override=getattr(args, "organization_override", None),
                data_variant=args.data_variant if args.benchmark == "dataclawbench" else None,
                source=runtime.source_manifest(), evaluator=evaluator, status="planned", model_calls_started=False,
                native_behavior="Requires matching offline native proof before execution; no quality claim")


def evaluator_manifest(upstream, benchmark):
    directory = upstream / ("evaluation" if benchmark == "hybriddeepresearch" else "dataclaw")
    result = {str(p.relative_to(upstream)): digest(p) for p in sorted(directory.rglob("*"))
              if p.is_file() and p.suffix in {".py", ".txt"}}
    if not result:
        raise ValueError("Missing upstream evaluator source")
    return result


def attempt(task, args, key):
    folder = args.output / task.id / args.backend
    work, profile = folder / "workspace", folder / "native-profile"
    work.mkdir(parents=True)
    (profile / "home").mkdir(parents=True)
    if task.benchmark == "dataclawbench":
        (work / "database").symlink_to("/data", target_is_directory=True)
    single = args.backend.endswith("single-agent")
    opts = runtime.options(args.backend)
    if getattr(args, "max_budget_usd", None) is not None:
        opts["max_budget_usd"] = args.max_budget_usd
    # The explicit helper keeps search-provider behavior consistent across modes.
    opts["disallowed_tools"] = ("WebSearch", "WebFetch")
    web_limit = run_web_limit(task, args)
    mode=getattr(args,'evidence_mode',None)
    rules=instructions(task,args.backend,getattr(args,'organization_override',None),timeout=args.timeout,
                       web_limit=web_limit,evidence_mode=mode)
    prompt = task.question + "\n\n" + rules
    result = dict(instance_id=task.id, final_answer="", status="not_started", cost_usd=None)
    runtime.write_json(folder / "report.json", result)
    identity = None
    gateway = None
    resources = None
    interrupted = None
    try:
        inputs = mounts(task, args) + [(Path(__file__).resolve().parents[2] / "harness/runtime_support/tools.py", "/benchmark-tools.py", True)] + evidence.source_mounts(mode)
        environment = {"MAS_BENCHMARK_WEB": "1" if task.web else "0", "MAS_WEB_LEDGER": "/native/web-usage.jsonl",
                       "MAS_WEB_PROVIDER": args.web_search or "none"}
        environment["MAS_WEB_MAX_REQUESTS"] = str(web_limit)
        gateway = CredentialGateway(key, unix_path=folder / "gateway.sock",
                                    ledger_path=folder / "gateway-requests.jsonl", web_limit=web_limit)
        gateway.__enter__()
        identity = runtime.container(work, profile, args.data, args.image, backend=args.backend, gateway=gateway,
            effort=getattr(args, "effort", "max"),
            dataset_mounts=inputs, environment_overrides=environment,
            forwarded_env=("TAVILY_API_KEY",) if task.web and args.web_search == "tavily" else ())
        if getattr(args,'record_resources',False):
            from harness.runtime_support.resources import ContainerResources
            resources=ContainerResources(identity,folder,2).start()
        result.update(status="running", container_id=identity, started_at=runtime.now())
        runtime.write_json(folder / "report.json", result)
        kwargs = dict(command_prefix=("docker", "exec", "-i", "--workdir", "/workspace", identity))
        kwargs.update(observer_dir=profile / "observer", observer_target="/native/observer", hook_script="/adapter-hooks.py")
        adapter = BACKENDS[args.backend](str(runtime.CLAUDE))
        if mode:
            native=evidence.launch(mode,runtime.CLAUDE,task.question,rules,work,folder,identity,
                worker_rules=instructions(task,args.backend,timeout=args.timeout,web_limit=web_limit,worker=True),
                model=opts['model'],allowed_tools=opts['allowed_tools'],disallowed_tools=opts['disallowed_tools'],
                timeout=args.timeout,max_budget_usd=getattr(args,'max_budget_usd',None))
        else:
            native = adapter.run(prompt, workspace=work, output=folder / "cli", timeout=args.timeout,
                                 execute=True, **opts, **kwargs)
        result.update(status=native["status"], cli=native)
    except BaseException as error:
        result.update(status="launcher_error", error=dict(type=type(error).__name__, message=str(error).replace(key, "[REDACTED]")))
        if getattr(error, "container_id", None):
            result.update(container_id=error.container_id, startup_cleanup=error.cleanup_details)
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            result["status"] = "interrupted"
            interrupted = error
    finally:
        if identity is not None:
            try:
                try:
                    try:
                        if resources is not None:
                            result['resources']=resources.close()
                    finally:
                        result["cleanup"] = runtime.stop_container(identity)
                    if resources is not None:
                        result['resources']=resources.record_exit()
                finally:
                    subprocess.run(["docker", "rm", identity], check=True, capture_output=True)
            except Exception as error:
                result.update(status="cleanup_failed", cleanup_error=type(error).__name__)
        if gateway is not None:
            gateway.__exit__(None, None, None)
            if hasattr(gateway, "summary"):
                result["gateway"] = gateway.summary()
        result["finished_at"] = runtime.now()
        if mode:
            try:
                result['evidence_workspace']=evidence.audit(folder,mode)
            except Exception as error:
                result['evidence_workspace']=dict(available=False,error_type=type(error).__name__)
        runtime.write_json(folder / "report.json", result)
    if interrupted is not None:
        raise interrupted
    if result["status"] == "cleanup_failed":
        return result
    result["integrity_audit"] = inspect_run(folder, args.backend)
    try:
        native_evidence = subprocess.run([sys.executable, "-I",
            str(Path(__file__).resolve().parents[2] / ("analysis/native_evidence.py")),
            "--backend", args.backend, "--profile", str(profile)], capture_output=True, text=True, timeout=120)
        if native_evidence.returncode == 0:
            result["accounting"] = json.loads(native_evidence.stdout)
        else:
            result["accounting_status"] = "native_reader_failed; usage and costs unknown"
    except (OSError, ValueError, subprocess.TimeoutExpired):
        result["accounting_status"] = "native_reader_unavailable; usage and costs unknown"
    try:
        audit = (native_single_agent if single else native_subagents)(folder)
        result["native_audit"] = audit
        if result["status"] == "cli_exited" and not audit["passed"]:
            result["status"] = "native_condition_unverified"
        if single and result["status"] == "cli_exited":
            accounting = result.get("accounting", {})
            if not accounting.get("observed_messages"):
                result["status"] = "single_agent_evidence_unverified"
            elif accounting.get("by_role", {}).get("member", {}).get("observed_messages", 0):
                result["status"] = "single_agent_condition_violated"
        submission = work / "submission.json"
        if submission.is_symlink() or not submission.is_file() or submission.stat().st_size > 1024 * 1024:
            raise ValueError("Missing, symlinked or oversized submission")
        data = json.loads(submission.read_text())
        if set(data) != {"final_answer"} or not isinstance(data["final_answer"], str):
            raise ValueError("Expected exactly one final_answer text field")
        if mode == 'full':
            result['decision_gate'] = evidence.host_check(folder, data)
            gate=result['decision_gate']
            result['protocol_status'] = ('coverage_unknown' if gate.get('coverage') is False
                else 'complete' if gate['accepted'] else 'incomplete')
        result["submission_sha256"] = digest(submission)
        shutil.copyfile(submission, folder / "submission.json")
        if evaluable_prediction(result):
            result["final_answer"] = data["final_answer"]
            if not data["final_answer"].strip():
                result["status"] = "incomplete"
    except (OSError, ValueError, KeyError, TypeError) as error:
        result["artifact_error"] = str(error)
        if result["status"] == "cli_exited":
            result["status"] = "incomplete"
    runtime.write_json(folder / "report.json", result)
    return result


def main(argv=None, *, benchmark=None):
    parser = argparse.ArgumentParser(description=__doc__)
    if benchmark is None:
        parser.add_argument("--benchmark", choices=("dataclawbench", "hybriddeepresearch"), required=True)
    else:
        parser.set_defaults(benchmark=benchmark)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--tasks", type=Path, help="HybridDeepResearch release JSONL, encrypted or private plaintext")
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--data-variant", choices=("database", "database_clear"), default="database")
    parser.add_argument("--backend", choices=BACKENDS, required=True)
    parser.add_argument("--task-id", action="append", required=True)
    parser.add_argument("--image", required=True, help="Existing image; never built or pulled here")
    parser.add_argument("--web-search", choices=("tavily", "deepseek"))
    parser.add_argument("--max-budget-usd", type=float, help="Native CLI per-attempt limit; not a provider invoice guarantee")
    parser.add_argument("--max-web-requests", type=int, help="Per-attempt paid web helper request limit across agents")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=None,
                        help="Solver seconds; defaults to the benchmark-specific timeout policy")
    parser.add_argument("--offline-proof", type=Path)
    parser.add_argument("--authorized-attempts", type=int)
    parser.add_argument("--credentials", type=Path, default=Path("/home/zhoujunye/mas/.env"))
    parser.add_argument("--execute", action="store_true")
    parser.add_argument('--record-resources',action='store_true')
    parser.add_argument("--effort", choices=("high", "max"), default="max")
    parser.add_argument("--organization-prompt", type=Path,
                        help="Explicit lead-only Claude Subagents study prompt override")
    parser.add_argument('--evidence-mode',choices=evidence.MODES)
    args = parser.parse_args(argv)
    args.organization_override = organization_override(args.organization_prompt, args.backend)
    evidence.validate_condition(args)
    if args.timeout is None:
        args.timeout = default_timeout(args.benchmark)
    if args.max_web_requests is None:
        args.max_web_requests = 4
    if args.execute and args.web_search == "tavily":
        parser.error("Paid Tavily execution is disabled until host-side credential isolation is implemented")
    if args.max_budget_usd is not None and (not math.isfinite(args.max_budget_usd) or args.max_budget_usd <= 0):
        parser.error("--max-budget-usd must be positive and finite")
    if args.max_web_requests is not None and args.max_web_requests < 1:
        parser.error("--max-web-requests must be positive")
    if args.timeout <= 0 or (args.benchmark == "hybriddeepresearch" and args.tasks is None):
        parser.error("Positive timeout and HybridDeepResearch --tasks are required")
    for name in ("upstream", "data", "output"):
        setattr(args, name, getattr(args, name).resolve())
    for source in (args.upstream, args.data):
        if args.output.is_relative_to(source) or source.is_relative_to(args.output):
            raise ValueError("Output and upstream/data paths must not overlap")
    if args.output.exists():
        raise ValueError("Use a fresh output directory, including after failed attempts")
    tasks = load(args)
    frozen = plan(args, tasks)
    if not args.execute:
        print(json.dumps(frozen, indent=2))
        return 0
    if args.authorized_attempts != len(tasks) or args.offline_proof is None:
        raise ValueError("Execution requires exact authorized attempt count and offline native proof")
    proof = json.loads(args.offline_proof.read_text())
    evidence.validate_proof(proof,args.evidence_mode)
    validate_proof(proof, args.backend)
    validate_effort(proof, args.effort)
    key = runtime.credential(args.credentials)
    args.image = json.loads(subprocess.check_output(["docker", "image", "inspect", args.image]))[0]["Id"]
    frozen.update(image_id=args.image, offline_proof_sha256=digest(args.offline_proof))
    binary = runtime.CLAUDE
    frozen["cli_binary"] = dict(path=str(binary), sha256=digest(binary))
    validate_runtime(proof, args.backend, image_id=args.image,
                     binary_sha256=frozen["cli_binary"]["sha256"])
    os.umask(0o077)
    args.output.mkdir(parents=True, exist_ok=False)
    runtime.write_json(args.output / "plan.json", frozen)
    with tarfile.open(args.output / "source.tgz", "w:gz") as archive:
        for relative, path in runtime.source_files():
            archive.add(path, arcname=str(relative), recursive=False)
    with graceful_signals():
        return execute_tasks(tasks, args, key)


def execute_tasks(tasks, args, key):
    rows = [dict(instance_id=t.id, final_answer="", status="not_started", cost_usd=None) for t in tasks]
    write_jsonl(args.output / "predictions.jsonl", rows)
    stopped = False
    for index, task in enumerate(tasks):
        if stopped:
            row = dict(instance_id=task.id, final_answer="", status="not_started", cost_usd=None)
        else:
            try:
                row = attempt(task, args, key)
            except (KeyboardInterrupt, SystemExit):
                rows[index].update(status="interrupted")
                write_jsonl(args.output / "predictions.jsonl", rows, replace=True)
                raise
            stopped = row["status"] != "cli_exited"
        rows[index] = row
        runtime.write_json(args.output / "progress.json", dict(rows=rows, expected=len(tasks)))
        write_jsonl(args.output / "predictions.jsonl", rows, replace=True)
    return 1 if stopped else 0


if __name__ == "__main__":
    raise SystemExit(main())
