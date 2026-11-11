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
from benchmarks.fdabench import tasks as fda
from harness import ClaudeCodeSingleAgentCLI, ClaudeCodeSubagentsCLI
from analysis.run_integrity import inspect_run
from harness.runtime_support import runtime
from harness.runtime_support.credential_gateway import CredentialGateway
from harness.runtime_support.proof import validate as validate_proof, validate_runtime, validate_effort
from benchmarks.policy import default_timeout, timeout_policy
from harness.runtime_support import web_policy
from analysis.native_evidence import native_single_agent, native_subagents, native_surface, single_agent_violated
from harness.runtime_support.admission import infrastructure_health
from common.io import fingerprint
from common.file_digest import DigestCache
from common.journal import exclusive

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
    tasks = (fda.load_tasks(args.tasks) if args.benchmark == "fdabench" else
             dataclaw_tasks(args.upstream) if args.benchmark == "dataclawbench" else hybrid_tasks(args.tasks))
    ids = args.task_id
    if not ids or len(ids) != len(set(ids)) or set(ids) - {t.id for t in tasks}:
        raise ValueError("Select explicit unique --task-id values from this dataset")
    by_id = {t.id: t for t in tasks}
    return [by_id[i] for i in ids]


def run_web_limit(task, args):
    """Run-wide web request limit shared by the prompt, helper ledger and host gateway."""
    return (getattr(args, "max_web_requests", None) or web_policy.DEFAULT_WEB_LIMIT) if task.web else 0


def instructions(task, backend, organization_override=None, *, timeout, web_limit=0):
    if web_limit and not task.web:
        raise ValueError("A web request limit requires a web-enabled task")
    common = "Do not install packages or seek benchmark questions, gold answers, reference SQL or solutions.\n"
    if task.benchmark == "dataclawbench":
        common += "The supplied database is read-only at /data; ./database points to it. Follow the original output guidelines.\n"
    elif task.benchmark == "fdabench":
        common += ("The selected read-only SQLite database is /data/database.sqlite. Discover its schema yourself.\n"
                   "Use python3 /benchmark-tools.py sql --db /data/database.sqlite --query SQL for read-only queries.\n")
        if fda.needs_corpus(task):
            common += "The raw reference corpus is read-only at /corpus. Inspect its documents locally; it contains no task answers.\n"
            common += "Search its local text index with python3 /document-tools.py --query TEXT. Results include source paths and pages.\n"
    else:
        common += (f"The read-only SQLite database is /data/{task.db}/{task.db}_template.sqlite.\n"
                   "Discover the schema yourself. A supplied *_kb.jsonl is optional domain knowledge, not a solution.\n"
                   "Use python3 /benchmark-tools.py sql --db PATH --query SQL for read-only queries.\n"
                   "Return concise text for entity/intersection questions; for a SQL question return one canonical query in a fenced sql block.\n")
    common += ("Web search/fetch are enabled: python3 /benchmark-tools.py search --query TEXT; "
               "python3 /benchmark-tools.py fetch --url URL. Search prints compact JSON lines; full results are shared files under /workspace/web.\n" if task.web else "No web search, fetching, or other external data access.\n")
    common += limit_instructions(timeout, web_limit)
    common += ('Write /workspace/submission.json with exactly {"final_answer": "your answer as text"}. '
               'If incomplete, use empty final_answer and explain in the CLI final response.\n')
    return common + condition_instructions(
        SimpleNamespace(organization_override=organization_override), backend)


def mounts(task, args):
    if task.benchmark == "fdabench":
        hash_file = DigestCache(args.asset_cache).digest if getattr(args, "asset_cache", None) else digest
        inputs = fda.mounts(task, args.data, hash_file=hash_file)
        if fda.needs_corpus(task):
            inputs.append((Path(__file__).resolve().parents[2] / "harness/runtime_support/documents.py", "/document-tools.py", True))
        return inputs
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
    condition_instructions(args, args.backend)
    expected = fda.REVISION if args.benchmark == "fdabench" else DC_REVISION if args.benchmark == "dataclawbench" else HDR_REVISION
    revision = subprocess.check_output(["git", "-C", str(args.upstream), "rev-parse", "HEAD"], text=True).strip()
    if revision != expected:
        raise ValueError("Upstream checkout does not match the documented source pin")
    verify_sources(args.upstream, args.benchmark)
    evaluator = evaluator_manifest(args.upstream, args.benchmark)
    assets = {}
    hash_file=DigestCache(args.asset_cache).digest if getattr(args,'asset_cache',None) else digest
    for task in tasks:
        for source, target, _ in mounts(task, args):
            if str(source) not in assets:
                assets[str(source)] = asset_manifest(source,hash_file=hash_file) if source.is_dir() else hash_file(source)
    prompts = {t.id: t.question + "\n\n" + instructions(t, args.backend, getattr(args, "organization_override", None),
                                                         timeout=args.timeout, web_limit=run_web_limit(t, args))
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
                cpu_per_attempt=getattr(args, 'cpus', runtime.DEFAULT_CPUS),compute_threads=getattr(args, 'compute_threads', runtime.DEFAULT_COMPUTE_THREADS),
                required_modules=runtime.capability_modules(getattr(args,'require_module',[])),
                capability_probes=runtime.capability_probes(getattr(args,'capability_probe',[])),
                asset_hash_policy='stat-validated-sha256-v1' if getattr(args,'asset_cache',None) else 'full-sha256',
                web_search=args.web_search,
                web_policy=web_policy.configuration(max(run_web_limit(t,args) for t in tasks)) if any(t.web for t in tasks) else None,
                web_request_limits={t.id: run_web_limit(t, args) for t in tasks},
                native_environment=runtime.native_env(args.backend, effort=getattr(args, "effort", runtime.DEFAULT_EFFORT),compute_threads=getattr(args, 'compute_threads', runtime.DEFAULT_COMPUTE_THREADS)),
                effort=getattr(args, "effort", runtime.DEFAULT_EFFORT),
                inference_policy=runtime.inference_configuration(getattr(args, 'effort', runtime.DEFAULT_EFFORT)),
                max_budget_usd=getattr(args, "max_budget_usd", None),
                max_web_requests=getattr(args, "max_web_requests", None),
                organization_prompt=condition_instructions(args, args.backend),
                organization_override=getattr(args, "organization_override", None),
                data_variant=args.data_variant if args.benchmark == "dataclawbench" else None,
                source=runtime.source_manifest(), evaluator=evaluator, status="planned", model_calls_started=False,
                native_behavior="Requires matching offline native proof before execution; no quality claim")


def evaluator_manifest(upstream, benchmark):
    directory = upstream / ("FDABench/evaluation" if benchmark == "fdabench" else
                            "evaluation" if benchmark == "hybriddeepresearch" else "dataclaw")
    result = {str(p.relative_to(upstream)): digest(p) for p in sorted(directory.rglob("*"))
              if p.is_file() and p.suffix in {".py", ".txt"}}
    if not result:
        raise ValueError("Missing upstream evaluator source")
    return result


def preflight(args,tasks,frozen):
    from harness.runtime_support.preflight import check
    from harness.runtime_support.web_fetch import check_ready_with_recovery as check_ready
    if any(t.web for t in tasks):
        runtime.write_json(args.output/'web-readiness.json',check_ready())
    checks=args.output/'preflight';checks.mkdir()
    rows=[]
    for task in tasks:
        folder=checks/task.id;work=folder/'workspace';profile=folder/'native-profile'
        work.mkdir(parents=True);(profile/'home').mkdir(parents=True)
        if task.benchmark in {'hybriddeepresearch', 'fdabench'}:
            path='/data/database.sqlite' if task.benchmark == 'fdabench' else f'/data/{task.db}/{task.db}_template.sqlite'
            code=(f'import sqlite3; c=sqlite3.connect("file:"+{path!r}+"?mode=ro",uri=True); '
                  'c.execute("PRAGMA query_only=ON"); c.execute("SELECT name FROM sqlite_master LIMIT 1").fetchall(); '
                  'c.close(); print("read-only database OK")')
            if task.benchmark == 'fdabench' and fda.needs_corpus(task):
                code += ('; import subprocess; subprocess.run(["python3", "/document-tools.py", '
                         '"--query", "data", "--limit", "1"], check=True, timeout=30, stdout=subprocess.DEVNULL); '
                         'from pathlib import Path; next(p for p in Path("/corpus").rglob("*") if p.is_file()).open("rb").close(); '
                         'print("read-only corpus and FTS index OK")')
        else:
            code='from pathlib import Path; p=next(p for p in Path("/data").rglob("*") if p.is_file()); f=p.open("rb"); f.read(80); f.close(); print("input mount readable")'
        source_mounts=mounts(task,args)+[(Path(__file__).resolve().parents[2]/'harness/runtime_support/tools.py','/benchmark-tools.py',True)]
        rows.append(check(work,profile,args.image,source_mounts,args.backend,args.effort,args.cpus,
            args.compute_threads,folder,['python3','-c',code],modules=args.require_module,
            probes=frozen['capability_probes'],record_resources=args.record_resources))
    runtime.write_json(args.output/'preflight-ok.json',dict(plan_sha256=fingerprint(frozen),paid_calls=0,checks=rows))


def attempt(task, args, key):
    condition_instructions(args, args.backend)
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
    rules=instructions(task,args.backend,getattr(args,'organization_override',None),timeout=args.timeout,
                       web_limit=web_limit)
    prompt = task.question + "\n\n" + rules
    result = dict(instance_id=task.id, final_answer="", status="not_started", cost_usd=None)
    runtime.write_json(folder / "report.json", result)
    identity = None
    gateway = None
    resources = None
    interrupted = None
    try:
        inputs = mounts(task, args) + [(Path(__file__).resolve().parents[2] / "harness/runtime_support/tools.py", "/benchmark-tools.py", True)]
        environment = {"MAS_BENCHMARK_WEB": "1" if task.web else "0",
                       "MAS_WEB_PROVIDER": args.web_search or "none"}
        environment["MAS_WEB_MAX_REQUESTS"] = str(web_limit)
        gateway = CredentialGateway(key, unix_path=folder / "gateway.sock",
                                    ledger_path=folder / "gateway-requests.jsonl", web_limit=web_limit,
                                    inference_policy=runtime.inference_configuration(getattr(args, 'effort', runtime.DEFAULT_EFFORT)))
        gateway.__enter__()
        identity = runtime.container(work, profile, args.data, args.image, backend=args.backend, gateway=gateway,
            effort=getattr(args, "effort", runtime.DEFAULT_EFFORT),
            cpus=getattr(args, 'cpus', runtime.DEFAULT_CPUS),compute_threads=getattr(args, 'compute_threads', runtime.DEFAULT_COMPUTE_THREADS),
            dataset_mounts=inputs, environment_overrides=environment)
        if getattr(args,'record_resources',False):
            from harness.runtime_support.resources import ContainerResources
            resources=ContainerResources(identity,folder,getattr(args, 'cpus', runtime.DEFAULT_CPUS)).start()
        result.update(status="running", container_id=identity, started_at=runtime.now())
        runtime.write_json(folder / "report.json", result)
        kwargs = dict(command_prefix=("docker", "exec", "-i", "--workdir", "/workspace", identity))
        kwargs.update(observer_dir=profile / "observer", observer_target="/native/observer", hook_script="/adapter-hooks.py")
        adapter = BACKENDS[args.backend](str(runtime.CLAUDE))
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
                        if result['status'] != 'cli_exited':
                            result['cleanup'] = runtime.stop_container(identity)
                        if resources is not None:
                            result['resources']=resources.close(final_sample=result['status'] == 'cli_exited')
                    finally:
                        if not result.get('cleanup', {}).get('stopped'):
                            result["cleanup"] = runtime.stop_container(identity)
                    if resources is not None:
                        result['resources']=resources.record_exit()
                finally:
                    subprocess.run(["docker", "rm", "-f", identity], check=True, capture_output=True, timeout=15)
            except Exception as error:
                result.update(status="cleanup_failed", cleanup_error=type(error).__name__)
        if gateway is not None:
            try:
                gateway.__exit__(None, None, None)
                if hasattr(gateway, "summary"):
                    result["gateway"] = gateway.summary()
            except Exception as error:
                result.update(status="cleanup_failed", gateway_cleanup_error=type(error).__name__)
        result["finished_at"] = runtime.now()
        result.update(infrastructure_health(folder / 'gateway-requests.jsonl'))
        runtime.write_json(folder / "report.json", result)
    if interrupted is not None:
        raise interrupted
    return finalize_attempt(folder,args,result)


def finalize_attempt(folder,args,result):
    """Host-only postprocessing, also usable after a quiescent solver crash."""
    work,profile=folder/'workspace',folder/'native-profile'
    single=args.backend.endswith('single-agent')
    if result["status"] == "cleanup_failed":
        return result
    result["integrity_audit"] = inspect_run(folder, args.backend)
    result['native_surface'] = native_surface(folder)
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
        accounting = result.get('accounting', {})
        if single and single_agent_violated(audit, accounting):
            result['condition_status'] = 'single_agent_condition_violated'
            if result['status'] in {'cli_exited', 'native_condition_unverified'}:
                result['status'] = 'single_agent_condition_violated'
        elif result["status"] == "cli_exited" and not audit["passed"]:
            result["status"] = "native_condition_unverified"
        if single and result["status"] == "cli_exited":
            accounting = result.get("accounting", {})
            if not accounting.get("observed_messages"):
                result["status"] = "single_agent_evidence_unverified"
        submission = work / "submission.json"
        if submission.is_symlink() or not submission.is_file() or submission.stat().st_size > 1024 * 1024:
            raise ValueError("Missing, symlinked or oversized submission")
        data = json.loads(submission.read_text())
        if set(data) != {"final_answer"} or not isinstance(data["final_answer"], str):
            raise ValueError("Expected exactly one final_answer text field")
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
        parser.add_argument("--benchmark", choices=("dataclawbench", "hybriddeepresearch", "fdabench"), required=True)
    else:
        parser.set_defaults(benchmark=benchmark)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--tasks", type=Path, help="HDR release JSONL or FDABench release directory/JSONL")
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--data-variant", choices=("database", "database_clear"), default="database")
    parser.add_argument("--backend", choices=BACKENDS, required=True)
    parser.add_argument("--task-id", action="append", required=True)
    parser.add_argument("--image", required=True, help="Existing image; never built or pulled here")
    parser.add_argument("--web-search", choices=("deepseek",))
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
    parser.add_argument('--cpus',type=int,choices=range(1,129),default=runtime.DEFAULT_CPUS)
    parser.add_argument('--compute-threads',type=int,choices=range(1,129),default=runtime.DEFAULT_COMPUTE_THREADS)
    parser.add_argument('--require-module',action='append',default=[])
    parser.add_argument('--capability-probe',action='append',default=[])
    parser.add_argument('--asset-cache',type=Path,help='Host-only stat-validated input hash cache; never mounted')
    parser.add_argument('--preflight',action='store_true',help='Freeze plan and check actual no-network container without model calls')
    parser.add_argument('--from-plan',action='store_true',help='Execute only after matching the saved preflight plan')
    parser.add_argument("--effort", choices=runtime.EFFORTS, default=runtime.DEFAULT_EFFORT,
                        help="none disables thinking and fixes temperature=0; high/max explicitly enable thinking")
    parser.add_argument("--organization-prompt", type=Path,
                        help="Explicit lead-only Claude Subagents study prompt override")
    args = parser.parse_args(argv)
    args.require_module=runtime.capability_modules(args.require_module)
    if args.compute_threads>args.cpus:parser.error('Compute threads exceed CPU quota')
    if args.preflight and (args.execute or args.from_plan):parser.error('Preflight is separate from execution')
    if args.from_plan and not args.execute:parser.error('--from-plan requires --execute')
    args.organization_override = organization_override(args.organization_prompt, args.backend)
    if args.timeout is None:
        args.timeout = default_timeout(args.benchmark)
    if args.max_web_requests is None:
        args.max_web_requests = web_policy.DEFAULT_WEB_LIMIT
    if args.max_budget_usd is not None and (not math.isfinite(args.max_budget_usd) or args.max_budget_usd <= 0):
        parser.error("--max-budget-usd must be positive and finite")
    if args.max_web_requests is not None and args.max_web_requests < 1:
        parser.error("--max-web-requests must be positive")
    if args.timeout <= 0 or (args.benchmark in {"hybriddeepresearch", "fdabench"} and args.tasks is None):
        parser.error("Positive timeout and HDR/FDABench --tasks are required")
    for name in ("upstream", "data", "output"):
        setattr(args, name, getattr(args, name).resolve())
    for source in (args.upstream, args.data):
        if args.output.is_relative_to(source) or source.is_relative_to(args.output):
            raise ValueError("Output and upstream/data paths must not overlap")
    if args.asset_cache:
        args.asset_cache=args.asset_cache.resolve()
        if any(args.asset_cache.is_relative_to(p) for p in [args.upstream,args.data,args.output]):
            raise ValueError('Hash cache must stay host-side outside inputs and attempt output')
    if args.output.exists() and not args.from_plan:
        raise ValueError("Use a fresh output directory, including after failed attempts")
    tasks = load(args)
    frozen = plan(args, tasks)
    if not args.execute and not args.preflight:
        print(json.dumps(frozen, indent=2))
        return 0
    if (args.execute and args.authorized_attempts != len(tasks)) or args.offline_proof is None:
        raise ValueError("Execution requires exact authorized attempt count and offline native proof")
    proof = json.loads(args.offline_proof.read_text())
    validate_proof(proof, args.backend)
    validate_effort(proof, args.effort)
    args.image = json.loads(subprocess.check_output(["docker", "image", "inspect", args.image]))[0]["Id"]
    frozen.update(image_id=args.image, offline_proof_sha256=digest(args.offline_proof))
    binary = runtime.CLAUDE
    frozen["cli_binary"] = dict(path=str(binary), sha256=digest(binary))
    validate_runtime(proof, args.backend, image_id=args.image,
                     binary_sha256=frozen["cli_binary"]["sha256"])
    os.umask(0o077)
    if args.from_plan:
        saved=json.loads((args.output/'plan.json').read_text())
        receipt=json.loads((args.output/'preflight-ok.json').read_text())
        if fingerprint(frozen)!=fingerprint(saved) or receipt['plan_sha256']!=fingerprint(saved):
            raise ValueError('Frozen plan or runtime/input settings changed')
        if (args.output/'predictions.jsonl').exists():raise ValueError('Attempt already started; never replay')
    else:
        args.output.mkdir(parents=True, exist_ok=False)
    if args.preflight or not args.from_plan:
        runtime.write_json(args.output/'plan.json',frozen)
        preflight(args,tasks,frozen)
        if args.preflight:return 0
    with exclusive(args.output/'execution.lock'):
        if any(t.web for t in tasks):
            from harness.runtime_support.web_fetch import check_ready_with_recovery as check_ready
            runtime.write_json(args.output/'web-readiness-execution.json',check_ready())
        with (args.output/'execution-claim.json').open('x') as stream:
            json.dump(dict(plan_sha256=fingerprint(frozen),status='dispatch_unknown',retries=0),stream)
            stream.flush();os.fsync(stream.fileno())
        key = runtime.credential(args.credentials)
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
                if index and task.web:
                    from harness.runtime_support.web_fetch import check_ready_with_recovery as check_ready
                    try:
                        receipt = check_ready()
                    except Exception as error:
                        row = dict(instance_id=task.id, final_answer="", status="not_started", cost_usd=None,
                                   dispatch_blocked='web_readiness_failed', error_type=type(error).__name__)
                        runtime.write_json(args.output/task.id/args.backend/'report.json', row)
                        rows[index] = row
                        runtime.write_json(args.output/'progress.json', dict(rows=rows, expected=len(tasks)))
                        write_jsonl(args.output/'predictions.jsonl', rows, replace=True)
                        stopped = True
                        continue
                    runtime.write_json(args.output/task.id/args.backend/'web-readiness-execution.json', receipt)
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
