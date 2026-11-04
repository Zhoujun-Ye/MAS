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
from benchmarks._external import asset_manifest, digest, verify_sources, write_jsonl
from benchmarks.dataclawbench.tasks import load_tasks as dataclaw_tasks, REVISION as DC_REVISION
from benchmarks.hybriddeepresearch.tasks import load_tasks as hybrid_tasks, REVISION as HDR_REVISION
from harness import ClaudeCodeSingleAgentCLI, ClaudeCodeSubagentsCLI, CodexSingleAgentCLI, CodexSubagentsCLI
from analysis.codex_evidence import inspect as codex_evidence
from analysis.run_integrity import inspect_run
from scripts.common import runtime
from scripts.common.credential_gateway import CredentialGateway
from scripts.common.proof import validate as validate_proof, validate_runtime
from scripts.common.timeouts import default_timeout, timeout_policy
from analysis.native_evidence import native_single_agent, native_subagents

BACKENDS = {"claude-code-single-agent": ClaudeCodeSingleAgentCLI, "claude-code-subagents": ClaudeCodeSubagentsCLI,
            "codex-single-agent": CodexSingleAgentCLI, "codex-subagents": CodexSubagentsCLI}


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


def instructions(task, backend, organization_override=None):
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
    common += ('Write /workspace/submission.json with exactly {"final_answer": "your answer as text"}. '
               'If incomplete, use empty final_answer and explain in the CLI final response.\n')
    return common + runtime.condition_instructions(
        SimpleNamespace(organization_override=organization_override), backend)


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
    prompts = {t.id: t.question + "\n\n" + instructions(t, args.backend, getattr(args, "organization_override", None)) for t in tasks}
    options = runtime.options(args.backend)
    if any(t.web for t in tasks) and not args.web_search:
        raise ValueError("This selection requires explicit --web-search; no silent web-free substitution")
    return dict(benchmark=args.benchmark, backend=args.backend, revision=revision,
                task_ids=[t.id for t in tasks], task_sources={t.id: t.source_sha256 for t in tasks},
                prompts={k: dict(sha256=hashlib.sha256(v.encode()).hexdigest(), characters=len(v),
                                 utf8_bytes=len(v.encode())) for k, v in prompts.items()},
                assets=assets, attempts=len(tasks), retries=0, judge_calls=0, options=options,
                image=args.image, network="none", timeout=args.timeout, timeout_policy=timeout_policy(args.benchmark, args.timeout),
                web_search=args.web_search,
                native_environment=runtime.native_env(args.backend),
                max_budget_usd=getattr(args, "max_budget_usd", None),
                codex_docker_isolated=getattr(args, "codex_docker_isolated", False),
                max_web_requests=getattr(args, "max_web_requests", None),
                organization_prompt=runtime.condition_instructions(args, args.backend),
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
    codex = args.backend.startswith("codex-")
    opts = runtime.options(args.backend)
    if codex:
        opts["docker_isolated"] = getattr(args, "codex_docker_isolated", False)
    if getattr(args, "max_budget_usd", None) is not None:
        opts["max_budget_usd"] = args.max_budget_usd
    # The explicit helper keeps search-provider behavior consistent across modes.
    if not codex:
        opts["disallowed_tools"] = ("WebSearch", "WebFetch")
    prompt = task.question + "\n\n" + instructions(task, args.backend, getattr(args, "organization_override", None))
    result = dict(instance_id=task.id, final_answer="", status="not_started", cost_usd=None)
    runtime.write_json(folder / "report.json", result)
    identity = None
    gateway = None
    interrupted = None
    try:
        inputs = mounts(task, args) + [(Path(__file__).with_name("tools.py"), "/benchmark-tools.py", True)]
        environment = {"MAS_BENCHMARK_WEB": "1" if task.web else "0", "MAS_WEB_LEDGER": "/native/web-usage.jsonl",
                       "MAS_WEB_PROVIDER": args.web_search or "none"}
        web_limit = (getattr(args, "max_web_requests", None) or 4) if task.web else 0
        environment["MAS_WEB_MAX_REQUESTS"] = str(web_limit)
        gateway = CredentialGateway(key, unix_path=folder / "gateway.sock",
                                    ledger_path=folder / "gateway-requests.jsonl", web_limit=web_limit)
        gateway.__enter__()
        if codex:
            opts["base_url"] = gateway.url
        identity = runtime.container(work, profile, args.data, args.image, backend=args.backend, gateway=gateway,
            dataset_mounts=inputs, environment_overrides=environment,
            forwarded_env=("TAVILY_API_KEY",) if task.web and args.web_search == "tavily" else ())
        result.update(status="running", container_id=identity, started_at=runtime.now())
        runtime.write_json(folder / "report.json", result)
        kwargs = dict(command_prefix=("docker", "exec", "-i", "--workdir", "/workspace", identity))
        if codex:
            kwargs.update(profile=profile / "codex", profile_target="/native/codex")
        else:
            kwargs.update(observer_dir=profile / "observer", observer_target="/native/observer", hook_script="/adapter-hooks.py")
        adapter = BACKENDS[args.backend](str(runtime.CODEX if codex else runtime.CLAUDE))
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
                result["cleanup"] = runtime.stop_container(identity)
                subprocess.run(["docker", "rm", identity], check=True, capture_output=True)
            except Exception as error:
                result.update(status="cleanup_failed", cleanup_error=type(error).__name__)
        if gateway is not None:
            gateway.__exit__(None, None, None)
            if hasattr(gateway, "summary"):
                result["gateway"] = gateway.summary()
        result["finished_at"] = runtime.now()
        runtime.write_json(folder / "report.json", result)
    if interrupted is not None:
        raise interrupted
    if result["status"] == "cleanup_failed":
        return result
    result["integrity_audit"] = inspect_run(folder, args.backend)
    try:
        evidence = subprocess.run([sys.executable, "-I",
            str(Path(__file__).resolve().parents[2] / ("analysis/codex_evidence.py" if codex else "analysis/native_evidence.py")),
            "--backend", args.backend, "--profile", str(profile)], capture_output=True, text=True, timeout=120)
        if evidence.returncode == 0:
            result["accounting"] = json.loads(evidence.stdout)
        else:
            result["accounting_status"] = "native_reader_failed; usage and costs unknown"
    except (OSError, ValueError, subprocess.TimeoutExpired):
        result["accounting_status"] = "native_reader_unavailable; usage and costs unknown"
    try:
        audit = codex_evidence(profile / "codex", single=single) if codex else (native_single_agent if single else native_subagents)(folder)
        result["native_audit"] = audit
        if result["status"] == "cli_exited" and not audit["passed"]:
            result["status"] = "native_condition_unverified"
        if single and not codex and result["status"] == "cli_exited":
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
        result["submission_sha256"] = digest(submission)
        shutil.copyfile(submission, folder / "submission.json")
        if result["status"] == "cli_exited":
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
    parser.add_argument("--credentials", type=Path, default=Path("/home/zhoujunye/MAS-information/.env"))
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--organization-prompt", type=Path,
                        help="Explicit lead-only Claude Subagents study prompt override")
    parser.add_argument("--codex-docker-isolated", action="store_true", help="Authorized opt-out of inner Codex sandbox; Docker isolation remains")
    args = parser.parse_args(argv)
    args.organization_override = runtime.organization_override(args.organization_prompt, args.backend)
    if args.timeout is None:
        args.timeout = default_timeout(args.benchmark)
    if args.max_web_requests is None:
        args.max_web_requests = 4
    if args.execute and args.web_search == "tavily":
        parser.error("Paid Tavily execution is disabled until host-side credential isolation is implemented")
    if args.backend.startswith("codex-") and args.max_budget_usd is not None:
        parser.error("Codex does not support the Claude dollar-budget option")
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
    validate_proof(proof, args.backend)
    if any(t.web for t in tasks) and args.web_search == "tavily" and not os.environ.get("TAVILY_API_KEY"):
        os.environ["TAVILY_API_KEY"] = runtime.credential(args.credentials, "TAVILY_API_KEY")
    key = runtime.credential(args.credentials)
    args.image = json.loads(subprocess.check_output(["docker", "image", "inspect", args.image]))[0]["Id"]
    frozen.update(image_id=args.image, offline_proof_sha256=digest(args.offline_proof))
    binary = runtime.CODEX if args.backend.startswith("codex-") else runtime.CLAUDE
    frozen["cli_binary"] = dict(path=str(binary), sha256=digest(binary))
    if args.backend.startswith("codex-"):
        frozen["model_catalog_sha256"] = digest(runtime.CODEX_CATALOG.with_name("deepseek-single-models.json")
                                                if args.backend == "codex-single-agent" else runtime.CODEX_CATALOG)
    validate_runtime(proof, args.backend, image_id=args.image,
                     binary_sha256=frozen["cli_binary"]["sha256"],
                     catalog_sha256=frozen.get("model_catalog_sha256"))
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
