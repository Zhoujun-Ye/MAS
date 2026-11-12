"""KramaBench-specific submission, pipeline replay and preparation lifecycle."""

from dataclasses import asdict
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.common.prompts.conditions import condition_instructions
from scripts.common.prompts.limits import limit_instructions
from common.io import fingerprint, write_json
from harness.runtime_support.resources import ContainerResources
from harness.runtime_support import runtime
from harness.runtime_support.preflight import check as check_container
from benchmarks.kramabench.evaluation import declared_incomplete, grade_answer, scoring_contract
from benchmarks.kramabench.tasks import load_tasks
from harness import ClaudeCodeSubagentsCLI, ClaudeCodeSingleAgentCLI
from harness.runtime_support.runtime import (CLAUDE, THREADS, container, native_env, now, options, snapshot, source_files, source_manifest, stop_container)
from scripts.kramabench.prepare import verify_inputs
from harness.runtime_support.credential_gateway import CredentialGateway
from analysis.native_evidence import native_single_agent, native_subagents, native_surface, single_agent_violated, timeout_waiting_evidence
from harness.runtime_support.admission import infrastructure_health
from analysis.run_integrity import inspect_run


SHARED_INSTRUCTIONS = """Solve the public data-analysis question using only the supplied input lake at /data.
The Python data-analysis environment is python3 at /usr/local/bin/python3.
Do not install packages, use network searches, or seek benchmark answers/reference solutions.
Inspect actual files and columns; check units, dates, missingness, joins and the requested estimand.
Save a runnable Python pipeline under /workspace, run it and check its printed answer.
The last nonempty pipeline stdout line must be exactly a JSON object with a single key:
{"answer": YOUR_ANSWER}. Use json.dumps, not prefixed text, prose, or extra diagnostic fields.
"""
SUBMISSION_INSTRUCTIONS = """Save /workspace/submission.json with exactly these keys:
answer (the requested scalar or list), pipeline_path (workspace-relative .py path),
evidence (a short string), unfinished (a list of strings).
Do not copy pipeline code into the final response. If incomplete, use null answer/path and explain unfinished.
"""
INSTRUCTIONS = SHARED_INSTRUCTIONS + SUBMISSION_INSTRUCTIONS


def submission(work):
    path = work / "submission.json"
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ValueError("Missing, nonregular or oversized submission.json")
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or set(data) != {"answer", "pipeline_path", "evidence", "unfinished"}:
        raise ValueError("Invalid submission fields")
    if not isinstance(data["evidence"], str) or not isinstance(data["unfinished"], list):
        raise ValueError("Invalid evidence/unfinished fields")
    if declared_incomplete(data):
        return data
    relative = data["pipeline_path"]
    if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("Missing or unsafe pipeline path")
    candidate = work / relative
    if any(p.is_symlink() for p in [candidate, *candidate.parents] if p != work.parent):
        raise ValueError("Symlink in pipeline path")
    candidate = candidate.resolve(strict=True)
    if not candidate.is_relative_to(work.resolve()) or candidate.suffix != ".py":
        raise ValueError("Pipeline must be a workspace .py file")
    return data


def replay_failure(name, code):
    """Docker's exit status alone cannot distinguish a launch error from sys.exit(125)."""
    state = None
    try:
        inspected = subprocess.run(['docker','inspect','--format','{{json .State}}',name],
                                   capture_output=True,text=True,timeout=15)
        if inspected.returncode==0:
            state=json.loads(inspected.stdout)
        started = datetime.fromisoformat(state['StartedAt'].replace('Z','+00:00')) if isinstance(state,dict) else None
        executed = (started is not None and started.year>1 and state.get('Error')==''
                    and state.get('Running') is False and state.get('Status')=='exited'
                    and type(state.get('ExitCode')) is int and state['ExitCode']==code)
    except (OSError,ValueError,KeyError,TypeError,subprocess.TimeoutExpired):
        executed=False
    return dict(status='runtime_error' if executed else 'harness_error',exit_code=code,
                execution_origin='container_process' if executed else 'docker_or_unverified',container_state=state)


def run_attempt(task, backend, args, key, stop, active, lock):
    folder = args.output / task.id / backend
    work, profile = folder / "workspace", folder / "native-profile"
    work.mkdir(parents=True)
    profile.mkdir(mode=0o700)
    (profile / "home").mkdir()
    instructions = INSTRUCTIONS + limit_instructions(args.timeout) + "\n" + condition_instructions(args, backend)
    # Readable task rules only. Isolated settings (--setting-sources "") do not auto-load
    # these files, so workers see them only if they read them; lead-only text stays in the prompt.
    (work / "AGENTS.md").write_text(INSTRUCTIONS)
    (work / "CLAUDE.md").write_text(INSTRUCTIONS)
    subprocess.run(["git", "init", "--quiet", str(work)], check=True)
    prompt = task.query + "\n\n" + instructions
    write_json(folder / "task.json", asdict(task))
    report, identity = dict(task_id=task.id, backend=backend, status="not_started"), None
    gateway = None
    resources = None
    if stop.is_set():
        write_json(folder / "report.json", report)
        return report
    try:
        gateway = CredentialGateway(key, unix_path=folder / "gateway.sock", web_limit=0,
                                    ledger_path=folder / "gateway-requests.jsonl",
                                    inference_policy=runtime.inference_configuration(getattr(args, 'effort', runtime.DEFAULT_EFFORT)))
        gateway.__enter__()
        identity = container(work, profile, args.upstream / "data", args.image,
                             gateway=gateway, backend=backend, effort=getattr(args, "effort", runtime.DEFAULT_EFFORT),
                             cpus=getattr(args, 'cpus', runtime.DEFAULT_CPUS), compute_threads=getattr(args, 'compute_threads', runtime.DEFAULT_COMPUTE_THREADS))
        if getattr(args, 'record_resources', False):
            resources = ContainerResources(identity, folder, args.cpus).start()
        with lock:
            active.add(identity)
        adapter = ({"claude-code-subagents": ClaudeCodeSubagentsCLI, "claude-code-single-agent": ClaudeCodeSingleAgentCLI}[backend](str(CLAUDE)))
        prefix = ("docker", "exec", "-i", "--workdir", "/workspace", identity)
        terminal_options = dict(command_prefix=prefix)
        terminal_options.update(observer_dir=profile/"observer", observer_target="/native/observer",
                                hook_script="/adapter-hooks.py")
        report.update(status="running", started_at=now(), container_id=identity)
        write_json(folder / "report.json", report)
        opts = options(backend)
        result = adapter.run(prompt, workspace=work, output=folder / "cli", timeout=args.timeout,
                             execute=True, **terminal_options, **opts)
        report.update(status=result["status"], cli=result, finished_at=now())
        # docker exec exiting (including timeout) does not stop its container.
        # Quiesce the solver before reading hooks, submissions or accounting.
        try:
            if result['status'] != 'cli_exited':
                report['cleanup'] = stop_container(identity)
            if resources is not None:
                report['resources'] = resources.close(final_sample=result['status'] == 'cli_exited')
        finally:
            if not report.get('cleanup', {}).get('stopped'):
                report["cleanup"] = stop_container(identity)
        write_json(folder / "report.json", report)
        report['native_surface'] = native_surface(folder)
        if backend == "claude-code-subagents":
            report["subagents_audit"] = native_subagents(folder)
            if report["subagents_audit"]["native_team_configs"] or report["subagents_audit"]["teammate_idle_events"]:
                stop.set()
                report['condition_status'] = 'native_mode_violation'
                if result['status'] == 'cli_exited':
                    report["status"] = "native_mode_violation"
            elif result["status"] == "cli_exited" and not report["subagents_audit"]["passed"]:
                report["status"] = "native_condition_unverified"
        if backend == "claude-code-single-agent":
            report["single_agent_audit"] = native_single_agent(folder)
            audit = report['single_agent_audit']
            violated = single_agent_violated(audit)
            if violated:
                stop.set()
                report['condition_status'] = 'single_agent_condition_violated'
            if result['status'] == 'cli_exited' and not audit['passed']:
                report['status'] = 'single_agent_condition_violated' if violated else 'native_condition_unverified'
        from harness.runtime_support.admission import fatal_provider_record
        # Transcript text includes untrusted data/tool output; only the host
        # ledger's upstream status is fatal evidence (as for DataClaw/HDR).
        fatal=fatal_provider_record(folder/'gateway-requests.jsonl')
        if fatal:
            stop.set()
            report["fatal_provider_error"] = True
            report['fatal_provider_evidence']=fatal
            with lock:
                owned = list(active)
            for owned_id in owned:
                subprocess.run(["docker", "stop", "--time", "1", owned_id], capture_output=True)
        write_json(folder / "report.json", report)
    except BaseException as error:
        report.update(status="launcher_error", error=dict(type=type(error).__name__, message=str(error).replace(key, "[REDACTED]")))
        if getattr(error, "container_id", None):
            report.update(container_id=error.container_id, startup_cleanup=error.cleanup_details)
            if not error.cleanup_details.get("removed"):
                with lock:
                    active.add(error.container_id)
                stop.set()
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            report["status"] = "interrupted"
            stop.set()
            raise
    finally:
        try:
            if identity is not None:
                try:
                    try:
                        if not report.get('cleanup', {}).get('stopped'):
                            report['cleanup'] = stop_container(identity)
                        if resources is not None:
                            report['resources'] = resources.close(final_sample=False)
                    finally:
                        if not report.get('cleanup', {}).get('stopped'):
                            report["cleanup"] = stop_container(identity)
                        if resources is not None:
                            report['resources']=resources.record_exit()
                    write_json(folder / "frozen-files.json", snapshot(work))
                finally:
                    subprocess.run(["docker", "rm", "-f", identity], check=True, capture_output=True, timeout=15)
                    with lock:
                        active.discard(identity)
        except Exception as error:
            report.update(status="cleanup_failed", cleanup_error=type(error).__name__)
            stop.set()
        finally:
            if gateway is not None:
                try:
                    gateway.__exit__(None, None, None)
                    if hasattr(gateway, "summary"):
                        report["gateway"] = gateway.summary()
                except Exception as error:
                    report.update(status='cleanup_failed',gateway_cleanup_error=type(error).__name__)
                    stop.set()
            report['finished_at']=now()
            report.update(infrastructure_health(folder / 'gateway-requests.jsonl'))
            report["integrity_audit"] = inspect_run(folder, backend)
            write_json(folder / "report.json", report)
    return report


def collect_attempt(folder, report, args):
    if 'decision_gate' in report:
        raise ValueError('Retired decision-gate attempts are read-only; use their recorded grades')
    backend, task_id = report["backend"], report["task_id"]
    if report["status"] == "not_started":
        return report
    reader = "analysis/native_evidence.py"
    evidence = subprocess.run([sys.executable, "-I", str(Path(__file__).resolve().parents[2] / reader),
                              "--backend", backend, "--profile", str(folder / "native-profile")],
                             capture_output=True, text=True, timeout=120)
    if evidence.returncode == 0:
        report["accounting"] = json.loads(evidence.stdout)
        write_json(folder / "native-accounting.json", report["accounting"])
        if backend == "claude-code-single-agent":
            report["single_agent_transcript_audit"] = dict(member_messages=report["accounting"].get(
                "by_role", {}).get("member", {}).get("observed_messages", 0))
            if report["single_agent_transcript_audit"]["member_messages"]:
                report['condition_status'] = 'single_agent_condition_violated'
                if report['status'] in {'cli_exited', 'native_condition_unverified'}:
                    report["status"] = "single_agent_condition_violated"
    else:
        report["accounting_error"] = evidence.stderr[-2000:]
        if backend == "claude-code-single-agent" and report['status'] == 'cli_exited':
            report["status"] = "single_agent_evidence_unverified"
    work = folder / "workspace"
    submission_valid=False
    submission_mtime=None
    report['pipeline_replay'] = dict(status='not_run', stage='submission_validation')
    try:
        raw_submission = work / "submission.json"
        if raw_submission.is_symlink() or not raw_submission.is_file() or raw_submission.stat().st_size > 1024 * 1024:
            report['pipeline_replay']['status'] = ('missing_submission' if not raw_submission.exists()
                and not raw_submission.is_symlink() else 'invalid_submission')
            raise ValueError("Submission is missing, oversized or nonregular")
        candidate = json.loads(raw_submission.read_text())
        if not isinstance(candidate, dict) or "answer" not in candidate:
            raise ValueError("Submission must contain answer")
        shutil.copyfile(raw_submission, folder / "submission.json")
        report["grade"] = grade_answer(args.upstream, task_id, folder / "submission.json")
        data = submission(work)
        submission_valid=data['answer'] is not None
        submission_mtime=raw_submission.stat().st_mtime
        report["submission"] = data
        if declared_incomplete(data):
            report['pipeline_replay']['status'] = 'incomplete_submission'
        else:
            # Never execute submitted code on the host; use a fresh offline copy.
            report['pipeline_replay']['stage'] = 'workspace_copy'
            replay = folder / "replay-workspace"
            shutil.copytree(work, replay, symlinks=True, ignore=shutil.ignore_patterns(".git"))
            name = "mas-cli6-replay-" + uuid.uuid4().hex[:10]
            write_json(folder/'replay/container-ownership.json',dict(container_name=name,status='creating'))
            command = ["docker", "run", "--pull", "never", "--name", name, "--network", "none",
                       "--cpus", str(getattr(args,'cpus',runtime.DEFAULT_CPUS)), "--memory", "8g", "--pids-limit", "256", "--cap-drop", "ALL",
                       "--security-opt", "no-new-privileges", "--user", f"{os.getuid()}:{os.getgid()}",
                       "--workdir", "/workspace", "--mount", f"type=bind,src={replay},dst=/workspace",
                       "--mount", f"type=bind,src={args.upstream / 'data'},dst=/data,readonly"]
            for key in THREADS:
                command += ["--env", key + "=" + str(getattr(args,'compute_threads',runtime.DEFAULT_COMPUTE_THREADS))]
            for key, value in runtime.REPRODUCIBLE_ENV.items():
                command += ["--env", key + "=" + value]
            command += [args.image, "python3", data["pipeline_path"]]
            report['pipeline_replay']['stage'] = 'execution'
            try:
                try:
                    executed = subprocess.run(command, capture_output=True, timeout=getattr(args, "replay_timeout", 180))
                except subprocess.TimeoutExpired as error:
                    report['pipeline_replay'].update(status='timed_out', timeout_seconds=getattr(args, 'replay_timeout', 180))
                    (folder / "pipeline-stdout.log").write_bytes(error.stdout or b"")
                    (folder / "pipeline-stderr.log").write_bytes(error.stderr or b"")
                    raise
                (folder / "pipeline-stdout.log").write_bytes(executed.stdout)
                (folder / "pipeline-stderr.log").write_bytes(executed.stderr)
                report["pipeline_exit_code"] = executed.returncode
                if executed.returncode:
                    failure=replay_failure(name,executed.returncode)
                    report['pipeline_replay'].update(failure)
                    report['artifact_error'] = dict(type='PipelineExecutionError' if failure['status']=='runtime_error' else 'DockerExecutionError',
                        message=f"Replay exit {executed.returncode}, origin {failure['execution_origin']}; see pipeline-stderr.log")
                else:
                    report['pipeline_replay']['stage'] = 'output_validation'
                    lines = executed.stdout.decode(errors="replace").strip().splitlines()
                    printed = json.loads(lines[-1]) if lines else None
                    report["pipeline_printed_answer"] = printed
                    valid = isinstance(printed, dict) and set(printed) == {"answer"}
                    report["pipeline_answer_matches_submission"] = valid and printed["answer"] == data["answer"]
                    report['pipeline_replay']['status'] = ('invalid_output' if not valid else
                        'matched' if report['pipeline_answer_matches_submission'] else 'answer_mismatch')
            finally:
                subprocess.run(["docker", "rm", "-f", name], capture_output=True)
    except Exception as error:
        report["artifact_error"] = dict(type=type(error).__name__, message=str(error))
        diagnostic = report['pipeline_replay']
        if diagnostic['status'] == 'not_run':
            diagnostic['status'] = {'submission_validation':'invalid_submission',
                'output_validation':'invalid_output'}.get(diagnostic['stage'], 'harness_error')
        if "grade" not in report:
            report["grade"] = grade_answer(args.upstream, task_id, None)
    if report['status'] == 'timed_out' or report.get('cli', {}).get('status') == 'timed_out':
        cutoff=report.get('cli',{}).get('timeout_observed_at')
        waiting=timeout_waiting_evidence(folder,cutoff)
        present=None
        if not submission_valid:
            present=False
        elif cutoff and submission_mtime is not None:
            try:
                stamp=datetime.fromisoformat(cutoff)
                if stamp.tzinfo is not None:
                    present=submission_mtime<=stamp.timestamp()
            except (ValueError,TypeError):
                pass
        idle=waiting['lead_idle_waiting']
        report['timeout_diagnostic']=dict(waiting,host_timeout_at=cutoff,submission_schema_valid=submission_valid,
            submission_present_at_deadline=present,
            lead_waiting_with_valid_submission=(False if idle is False or present is False else
                                              True if idle is True and present is True else None),
            submission_timing_basis='Post-cleanup file mtime compared to host timeout; cooperative evidence, not tamper protection',
            scoring_policy='Diagnostic only; timeout primary score remains zero')
        report['artifact_grade'] = report['grade']
        report['grade'] = dict(status='incomplete_timeout', score=0, judge_calls=0,
                               policy='Incomplete solvers receive zero; retained submission is diagnostic only')
    write_json(folder / "grade.json", report["grade"])
    write_json(folder / "report.json", report)
    return report


def input_inventory(args):
    path=getattr(args,'asset_cache',None)
    if path is None:return verify_inputs(args.upstream)
    from common.file_digest import DigestCache
    return verify_inputs(args.upstream,cache=DigestCache(path))


def preflight(args):
    tasks, provenance = load_tasks(args.upstream)
    selected_ids = getattr(args, "selected_task_ids", ())
    selected = tasks if getattr(args, "all_tasks", False) else [next(task for task in tasks if task.id == identity) for identity in selected_ids]
    backends = args.backends
    strict_single = any(b.endswith("single-agent") for b in backends)
    binaries = {"claude": CLAUDE for b in backends}
    scoring = scoring_contract(args.upstream)
    image = json.loads(subprocess.check_output(["docker", "image", "inspect", args.image]))[0]
    args.image = image["Id"]
    inventory = input_inventory(args)
    plan = dict(created_at=now(), tasks=[asdict(t) for t in selected], attempts=len(backends) * len(selected),
                backends=list(backends), concurrency=args.concurrency, strict_single=strict_single,
                timeout_seconds=args.timeout, retries=0, model="deepseek-flash", effort=getattr(args, "effort", runtime.DEFAULT_EFFORT),
                inference_policy=runtime.inference_configuration(getattr(args, 'effort', runtime.DEFAULT_EFFORT)),
                provenance=provenance, scoring=scoring, image_id=args.image, network="none",
                inputs_sha256=fingerprint(inventory), instructions=INSTRUCTIONS,
                asset_hash_policy='stat-validated-pinned-blob-v1' if getattr(args,'asset_cache',None) else 'full-hash',
                limit_instructions=limit_instructions(args.timeout),
                backend_options={b: options(b) for b in backends},
                backend_instructions={b: condition_instructions(args, b) for b in backends},
                organization_override=getattr(args, "organization_override", None),
                native_environment={b: native_env(b, effort=getattr(args, "effort", runtime.DEFAULT_EFFORT),
                    compute_threads=getattr(args, 'compute_threads', runtime.DEFAULT_COMPUTE_THREADS)) for b in backends},
                compute_threads=getattr(args, 'compute_threads', runtime.DEFAULT_COMPUTE_THREADS),
                required_modules=runtime.capability_modules(getattr(args, 'require_module', [])),
                capability_probes=runtime.capability_probes(getattr(args, 'capability_probe', [])),
                cpu_per_attempt=getattr(args, 'cpus', runtime.DEFAULT_CPUS), record_resources=getattr(args, 'record_resources', False), memory_per_attempt="8g",
                source=source_manifest(),
                judge_limit=getattr(args, "judge_limit", 0),
                replay_timeout_seconds=getattr(args, "replay_timeout", 180),
                cli_binaries={name: dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
                              for name, path in binaries.items()},
                requested_scope=f"{len(backends) * len(selected)} solver attempts and at most {getattr(args, 'judge_limit', 0)} semantic judge calls; explicit user authorization still required",
                comparison="Engineering pilot; native organizations differ; not causal architecture evidence")
    args.output.mkdir(parents=True, exist_ok=False)
    write_json(args.output / "plan.json", plan)
    write_json(args.output / "inputs.json", inventory)
    with tarfile.open(args.output / "source.tgz", "w:gz") as archive:
        for relative, path in source_files():
            archive.add(path, arcname=str(relative), recursive=False)
    checks = args.output / "preflight"
    checks.mkdir()
    work, profile = checks / "workspace", checks / "native-profile"
    work.mkdir()
    profile.mkdir()
    (profile / "home").mkdir()
    backend = backends[0]
    check_container(work, profile, args.image, [(args.upstream / 'data', '/data', True)],
        backend, getattr(args, 'effort', runtime.DEFAULT_EFFORT),
        getattr(args, 'cpus', runtime.DEFAULT_CPUS), getattr(args, 'compute_threads', runtime.DEFAULT_COMPUTE_THREADS),
        checks, ['python3', '-c', "import numpy,pandas,scipy,pypdf; print('domain imports OK')"],
        modules=getattr(args, 'require_module', []), probes=plan['capability_probes'],
        record_resources=getattr(args, 'record_resources', False))
    write_json(args.output / "preflight-ok.json", dict(paid_calls=0, plan_sha256=fingerprint(plan)))
    return selected, plan


def compact(report):
    return dict(task_id=report["task_id"], backend=report["backend"], status=report["status"],
                elapsed_seconds=report.get("cli", {}).get("elapsed_seconds"),
                fatal_provider_error=report.get("fatal_provider_error", False))
