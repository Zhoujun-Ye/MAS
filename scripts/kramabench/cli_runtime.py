"""Shared native-CLI benchmark process, container, artifact and evidence helpers."""

from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import shutil
import shlex
import stat
import subprocess
import sys
import tarfile
import urllib.request
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from benchmarks.kramabench._io import fingerprint, write_json
from benchmarks.kramabench.evaluation import grade_answer, scoring_contract
from benchmarks.kramabench.tasks import load_tasks
from harness import ClaudeCodeAgentTeamCLI, ClaudeCodeSubagentsCLI, ClaudeCodeSingleAgentCLI, DeepAgentsCLI
from harness._claude_hooks import BLOCKED_TOOLS
from harness.deepagents.single import audit_events, prepare_profile
from scripts.kramabench.prepare import verify_inputs
from scripts.kramabench.native_evidence import native_single_agent, native_subagents

CLAUDE = Path("/home/zhoujunye/.local/bin/claude").resolve()
DCODE = Path("/home/zhoujunye/.local/bin/dcode").resolve()
TOOL = Path("/home/zhoujunye/.local/share/uv/tools/deepagents-code")
PYTHON_ROOT = (TOOL / "bin/python").resolve().parent.parent
TOOLS = ("Bash", "Read", "Write", "Edit", "Glob", "Grep", "Agent", "SendMessage",
         "TaskCreate", "TaskUpdate", "TaskGet", "TaskList", "TaskStop", "TaskOutput")
THREADS = {name: "1" for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                                  "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")}
INSTRUCTIONS = """Solve the public data-analysis question using only the supplied input lake at /data.
The Python data-analysis environment is python3 at /usr/local/bin/python3.
Do not install packages, use network searches, or seek benchmark answers/reference solutions.
Inspect actual files and columns; check units, dates, missingness, joins and the requested estimand.
Save a runnable Python pipeline under /workspace, run it and check its printed answer.
The last nonempty pipeline stdout line must be exactly a JSON object with a single key:
{"answer": YOUR_ANSWER}. Use json.dumps, not prefixed text, prose, or extra diagnostic fields.
Save /workspace/submission.json with exactly these keys:
answer (the requested scalar or list), pipeline_path (workspace-relative .py path),
evidence (a short string), unfinished (a list of strings).
Do not copy pipeline code into the final response. If incomplete, use null answer/path and explain unfinished.
"""


def backend_instructions(backend):
    if backend in {"deepagents", "claude-code-single-agent"}:
        return ("This is the strict SINGLE-AGENT condition. Complete all work yourself. Native delegation "
                "is disabled by policy. Do not call task, spawn any subagent, or launch other model/agent "
                "processes through shell, Python, HTTP, or any other route. No external model calls.")
    if backend == "claude-code-subagents":
        return ("Use ordinary native Agent subagents for meaningful complementary work, with results returned to "
                "the main agent. Agent Teams is disabled; do not create or imitate a peer team. "
                "Do not impose a fixed roster or duplicate work. Finish delegated work and incorporate its findings "
                "before writing the final submission. Use native Agent/TaskOutput results, not sleep or shell polling.")
    return ("Use native Claude Code Agent Teams through named Agent teammates, not ordinary foreground subagents. "
            "Seek meaningful complementary deliverables without a fixed roster or duplicate work. "
            "Use concise SendMessage reports and synthesize delivered findings. When waiting for teammates, "
            "end the current turn so native messages can be delivered; do not sleep or poll with Bash. "
            "Yielding is not task completion: after reports arrive, finish the pipeline and submission.json. "
            "Finish delegated work before final completion. Never edit or delete native team/member state. "
            "This version uses implicit teams; TeamCreate/TeamDelete do not exist. Do not manufacture cleanup.")


def now():
    return datetime.now(timezone.utc).isoformat()


def source_files():
    root = Path(__file__).resolve().parents[2]
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in {"upstream", "assets", "__pycache__", ".git", "outputs", "archives", ".venv"}
               for part in relative.parts):
            continue
        if path.is_file() and path.suffix in {".py", ".md", ".toml", ".sh"}:
            yield relative, path


def source_manifest():
    return {str(relative): hashlib.sha256(path.read_bytes()).hexdigest() for relative, path in source_files()}


def credential(path):
    if stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise ValueError("Credential file must have mode 0600")
    values = {}
    for line in path.read_text().splitlines():
        words = shlex.split(line, comments=True)
        if not words:
            continue
        if len(words) != 1 or "=" not in words[0]:
            raise ValueError("Expected plain KEY=VALUE credential entries")
        key, value = words[0].split("=", 1)
        values[key] = value
    key = values.get("DEEPSEEK_API_KEY")
    if not key:
        raise ValueError("Missing DeepSeek key")
    return key


def balance(key):
    request = urllib.request.Request("https://api.deepseek.com/user/balance",
                                     headers={"Authorization": "Bearer " + key})
    with urllib.request.urlopen(request, timeout=30) as response:
        return dict(observed_at=now(), response=json.load(response))


def balance_deltas(before, after):
    def values(receipt):
        return {row["currency"]: Decimal(row["total_balance"])
                for row in receipt["response"]["balance_infos"]}
    first, last = values(before), values(after)
    if first.keys() != last.keys():
        raise ValueError("Balance currencies changed during the measured interval")
    return {currency: str(amount - last[currency]) for currency, amount in first.items()}


def snapshot(work):
    files = {}
    for parent, dirs, names in os.walk(work, followlinks=False):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in names:
            path = Path(parent) / name
            if path.is_file() and not path.is_symlink():
                files[str(path.relative_to(work))] = dict(bytes=path.stat().st_size,
                    sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            else:
                files[str(path.relative_to(work))] = dict(kind="symlink_or_special")
    return files


def submission(work):
    path = work / "submission.json"
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ValueError("Missing, nonregular or oversized submission.json")
    data = json.loads(path.read_text())
    if set(data) != {"answer", "pipeline_path", "evidence", "unfinished"}:
        raise ValueError("Invalid submission fields")
    if not isinstance(data["evidence"], str) or not isinstance(data["unfinished"], list):
        raise ValueError("Invalid evidence/unfinished fields")
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


def options(backend):
    if backend == "deepagents":
        return dict(model="anthropic:deepseek-flash", shell_allow_list="all", no_mcp=True,
                    summarization_model="anthropic:deepseek-flash",
                    model_params={"max_tokens": 16384, "thinking": {"type": "enabled", "budget_tokens": 8192},
                                  "output_config": {"effort": "max"}},
                    profile_override={"max_input_tokens": 1000000, "max_output_tokens": 16384},
                    single_agent=True, max_turns=500)
    tools = tuple(t for t in TOOLS if t not in BLOCKED_TOOLS) if backend == "claude-code-single-agent" else TOOLS
    return dict(model="deepseek-flash[1m]", allowed_tools=tools,
                disallowed_tools=("WebSearch", "WebFetch"), isolated_settings=True)


def native_env(backend):
    return dict(THREADS, HOME="/native/home", DEEPAGENTS_HOME="/native/deepagents",
                CLAUDE_CONFIG_DIR="/native/claude", ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic",
                ANTHROPIC_MODEL="deepseek-flash[1m]", ANTHROPIC_DEFAULT_OPUS_MODEL="deepseek-flash[1m]",
                ANTHROPIC_DEFAULT_SONNET_MODEL="deepseek-flash[1m]", ANTHROPIC_DEFAULT_HAIKU_MODEL="deepseek-flash",
                CLAUDE_CODE_SUBAGENT_MODEL="deepseek-flash[1m]", CLAUDE_CODE_EFFORT_LEVEL="max",
                CLAUDE_CODE_AUTO_COMPACT_WINDOW="786432", CLAUDE_CODE_MAX_OUTPUT_TOKENS="16384",
                CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS="1" if backend in {"claude-code-agent-team", "both"} else "0",
                CLAUDE_CODE_MAX_RETRIES="0",
                DISABLE_AUTOUPDATER="1", CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1",
                DEEPAGENTS_CODE_AUTO_UPDATE="0", DEEPAGENTS_CODE_NO_UPDATE_CHECK="1",
                DEEPAGENTS_CODE_PLUGIN_AUTO_UPDATE="0", DEEPAGENTS_CODE_PRICES_AUTO_UPDATE="0",
                DEEPAGENTS_CODE_MEMORY_AUTO_SAVE="0", DEEPAGENTS_CODE_EXTENSIONS="0",
                DEEPAGENTS_CODE_EXPERIMENTAL="0", LANGSMITH_TRACING="false", LANGCHAIN_TRACING_V2="false")


def container(work, profile, dataset, image, key=None, network="bridge", backend="both"):
    name = "mas-cli6-" + uuid.uuid4().hex[:12]
    environment = native_env(backend)
    args = ["docker", "run", "-d", "--pull", "never", "--name", name,
            "--label", "purpose=mas-information-cli6", "--network", network, "--cpus", "2",
            "--memory", "8g", "--pids-limit", "512", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--user", f"{os.getuid()}:{os.getgid()}",
            "--workdir", "/workspace"]
    for source, target, readonly in ((work, "/workspace", False), (profile, "/native", False),
                                    (dataset, "/data", True), (TOOL, str(TOOL), True),
                                    (PYTHON_ROOT, str(PYTHON_ROOT), True), (CLAUDE, str(CLAUDE), True),
                                    (Path(__file__).resolve().parents[2] / "harness/_claude_hooks.py", "/adapter-hooks.py", True)):
        args += ["--mount", f"type=bind,src={source},dst={target}" + (",readonly" if readonly else "")]
    policy = profile / "deepagents/hooks.json"
    if backend == "deepagents" and policy.exists():
        args += ["--mount", f"type=bind,src={policy},dst=/native/deepagents/hooks.json,readonly",
                 "--mount", "type=bind,src=" + str(Path(__file__).resolve().parents[2] / "harness/deepagents/hooks.py")
                 + ",dst=/adapter-single-hooks.py,readonly"]
    for name, value in environment.items():
        args += ["--env", name + "=" + value]
    # Values are inherited through docker's environment, never placed in argv or receipts.
    if backend in {"deepagents", "both"}:
        args += ["--env", "ANTHROPIC_API_KEY"]
    if backend != "deepagents":
        args += ["--env", "ANTHROPIC_AUTH_TOKEN"]
    args += [image, "sleep", "infinity"]
    return subprocess.check_output(args, env=dict(os.environ, ANTHROPIC_API_KEY=key or "offline-placeholder",
                                   ANTHROPIC_AUTH_TOKEN=key or "offline-placeholder"), text=True).strip()


def stop_container(identity):
    result = subprocess.run(["docker", "stop", "--time", "2", identity], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("Could not stop owned container: " + identity)
    return dict(stopped=True, container_id=identity)


def run_attempt(task, backend, args, key, stop, active, lock):
    folder = args.output / task.id / backend
    work, profile = folder / "workspace", folder / "native-profile"
    work.mkdir(parents=True)
    profile.mkdir(mode=0o700)
    (profile / "home").mkdir()
    strict_single = backend == "deepagents"
    instructions = INSTRUCTIONS + "\n" + backend_instructions(backend)
    (work / "AGENTS.md").write_text(instructions)
    (work / "CLAUDE.md").write_text(instructions)
    subprocess.run(["git", "init", "--quiet", str(work)], check=True)
    prompt = task.query + "\n\n" + instructions
    if backend == "deepagents" and strict_single:
        prepare_profile(profile / "deepagents", script="/adapter-single-hooks.py",
                        observer="/native/single-observer/events.jsonl")
    write_json(folder / "task.json", asdict(task))
    report, identity = dict(task_id=task.id, backend=backend, status="not_started"), None
    if stop.is_set():
        write_json(folder / "report.json", report)
        return report
    try:
        identity = container(work, profile, args.upstream / "data", args.image, key, backend=backend)
        with lock:
            active.add(identity)
        adapter = (DeepAgentsCLI(str(DCODE)) if backend == "deepagents" else
                   {"claude-code-agent-team": ClaudeCodeAgentTeamCLI,
                    "claude-code-subagents": ClaudeCodeSubagentsCLI,
                    "claude-code-single-agent": ClaudeCodeSingleAgentCLI}[backend](str(CLAUDE)))
        prefix = ("docker", "exec", "-i", "--workdir", "/workspace", identity)
        terminal_options = {}
        if backend == "claude-code-agent-team":
            terminal_options = dict(command_prefix=("docker", "exec", "-it", "--workdir", "/workspace", identity),
                version_prefix=prefix, observer_dir=profile / "observer", observer_target="/native/observer",
                hook_script="/adapter-hooks.py", hook_python="python3", cli_workspace="/workspace",
                native_profile=profile / "claude", completion_file="submission.json")
        else:
            terminal_options = dict(command_prefix=prefix)
            if strict_single:
                terminal_options.update(policy_profile=profile / "deepagents", profile_target="/native/deepagents")
            else:
                terminal_options.update(observer_dir=profile/"observer", observer_target="/native/observer",
                                        hook_script="/adapter-hooks.py")
        report.update(status="running", started_at=now(), container_id=identity)
        write_json(folder / "report.json", report)
        result = adapter.run(prompt, workspace=work, output=folder / "cli", timeout=args.timeout,
                             execute=True, **terminal_options, **options(backend))
        report.update(status=result["status"], cli=result, finished_at=now())
        if backend == "deepagents" and strict_single:
            report["single_agent_audit"] = audit_events(profile / "single-observer/events.jsonl")
            if not report["single_agent_audit"]["passed"]:
                stop.set()
                report["status"] = "single_agent_policy_unverified"
        if backend == "claude-code-subagents":
            report["subagents_audit"] = native_subagents(folder)
            if report["subagents_audit"]["native_team_configs"] or report["subagents_audit"]["teammate_idle_events"]:
                stop.set()
                report["status"] = "native_mode_violation"
        if backend == "claude-code-single-agent":
            report["single_agent_audit"] = native_single_agent(folder)
            if not report["single_agent_audit"]["passed"]:
                stop.set()
                report["status"] = "single_agent_policy_unverified"
        error_text = "\n".join(p.read_text(errors="replace")[-32000:] for p in
                               (folder / "cli/stdout.log", folder / "cli/stderr.log") if p.exists()).lower()
        if result["status"] != "cli_exited" and any(marker in error_text for marker in
                ("insufficient balance", "invalid api key", "authentication_error", "credit balance is too low")):
            stop.set()
            report["fatal_provider_error"] = True
            with lock:
                owned = list(active)
            for owned_id in owned:
                subprocess.run(["docker", "stop", "--time", "1", owned_id], capture_output=True)
        write_json(folder / "report.json", report)
    except BaseException as error:
        report.update(status="launcher_error", error=dict(type=type(error).__name__, message=str(error)))
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            stop.set()
            raise
    finally:
        if identity is not None:
            try:
                report["cleanup"] = stop_container(identity)
                write_json(folder / "frozen-files.json", snapshot(work))
            finally:
                subprocess.run(["docker", "rm", identity], capture_output=True)
                with lock:
                    active.discard(identity)
        write_json(folder / "report.json", report)
    return report


def collect_attempt(folder, report, args):
    backend, task_id = report["backend"], report["task_id"]
    if report["status"] == "not_started":
        return report
    evidence = subprocess.run([str(TOOL / "bin/python"), "-I", str(Path(__file__).with_name("native_evidence.py")),
                              "--backend", backend, "--profile", str(folder / "native-profile")],
                             capture_output=True, text=True, timeout=120)
    if evidence.returncode == 0:
        report["accounting"] = json.loads(evidence.stdout)
        write_json(folder / "native-accounting.json", report["accounting"])
        if backend == "deepagents":
            report["single_agent_checkpoint_audit"] = dict(member_messages=report["accounting"].get(
                "by_role", {}).get("member", {}).get("observed_messages", 0))
            if report["single_agent_checkpoint_audit"]["member_messages"]:
                report["status"] = "single_agent_condition_violated"
        if backend == "claude-code-single-agent":
            report["single_agent_transcript_audit"] = dict(member_messages=report["accounting"].get(
                "by_role", {}).get("member", {}).get("observed_messages", 0))
            if report["single_agent_transcript_audit"]["member_messages"]:
                report["status"] = "single_agent_condition_violated"
    else:
        report["accounting_error"] = evidence.stderr[-2000:]
        if backend == "claude-code-single-agent":
            report["status"] = "single_agent_evidence_unverified"
    work = folder / "workspace"
    try:
        raw_submission = work / "submission.json"
        if raw_submission.is_symlink() or not raw_submission.is_file() or raw_submission.stat().st_size > 1024 * 1024:
            raise ValueError("Submission is missing, oversized or nonregular")
        candidate = json.loads(raw_submission.read_text())
        if not isinstance(candidate, dict) or "answer" not in candidate:
            raise ValueError("Submission must contain answer")
        shutil.copyfile(raw_submission, folder / "submission.json")
        report["grade"] = grade_answer(args.upstream, task_id, folder / "submission.json")
        data = submission(work)
        report["submission"] = data
        # Never execute submitted code on the host; use a fresh offline copy.
        replay = folder / "replay-workspace"
        shutil.copytree(work, replay, symlinks=True, ignore=shutil.ignore_patterns(".git"))
        name = "mas-cli6-replay-" + uuid.uuid4().hex[:10]
        command = ["docker", "run", "--rm", "--pull", "never", "--name", name, "--network", "none",
                   "--cpus", "2", "--memory", "8g", "--pids-limit", "256", "--cap-drop", "ALL",
                   "--security-opt", "no-new-privileges", "--user", f"{os.getuid()}:{os.getgid()}",
                   "--workdir", "/workspace", "--mount", f"type=bind,src={replay},dst=/workspace",
                   "--mount", f"type=bind,src={args.upstream / 'data'},dst=/data,readonly"]
        for key, value in THREADS.items():
            command += ["--env", key + "=" + value]
        command += [args.image, "python3", data["pipeline_path"]]
        try:
            try:
                executed = subprocess.run(command, capture_output=True, timeout=getattr(args, "replay_timeout", 180))
            except subprocess.TimeoutExpired as error:
                (folder / "pipeline-stdout.log").write_bytes(error.stdout or b"")
                (folder / "pipeline-stderr.log").write_bytes(error.stderr or b"")
                raise
            (folder / "pipeline-stdout.log").write_bytes(executed.stdout)
            (folder / "pipeline-stderr.log").write_bytes(executed.stderr)
            report["pipeline_exit_code"] = executed.returncode
            lines = executed.stdout.decode(errors="replace").strip().splitlines()
            printed = json.loads(lines[-1]) if lines else None
            report["pipeline_printed_answer"] = printed
            report["pipeline_answer_matches_submission"] = (
                isinstance(printed, dict) and set(printed) == {"answer"} and printed["answer"] == data["answer"])
        finally:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True)
    except Exception as error:
        report["artifact_error"] = dict(type=type(error).__name__, message=str(error))
        if "grade" not in report:
            report["grade"] = grade_answer(args.upstream, task_id, None)
    write_json(folder / "grade.json", report["grade"])
    write_json(folder / "report.json", report)
    return report


def preflight(args):
    tasks, provenance = load_tasks(args.upstream)
    selected_ids = getattr(args, "selected_task_ids", ())
    selected = tasks if getattr(args, "all_tasks", False) else [next(task for task in tasks if task.id == identity) for identity in selected_ids]
    backends = args.backends
    strict_single = bool({"deepagents", "claude-code-single-agent"} & set(backends))
    scoring = scoring_contract(args.upstream)
    image = json.loads(subprocess.check_output(["docker", "image", "inspect", args.image]))[0]
    args.image = image["Id"]
    inventory = verify_inputs(args.upstream)
    plan = dict(created_at=now(), tasks=[asdict(t) for t in selected], attempts=len(backends) * len(selected),
                backends=list(backends), concurrency=args.concurrency, strict_single=strict_single,
                timeout_seconds=args.timeout, retries=0, model="deepseek-flash", effort="max",
                provenance=provenance, scoring=scoring, image_id=args.image,
                inputs_sha256=fingerprint(inventory), instructions=INSTRUCTIONS,
                backend_options={b: options(b) for b in backends},
                backend_instructions={b: backend_instructions(b) for b in backends},
                native_environment={b: native_env(b) for b in backends}, cpu_per_attempt=2, memory_per_attempt="8g",
                source=source_manifest(),
                judge_limit=getattr(args, "judge_limit", 0),
                replay_timeout_seconds=getattr(args, "replay_timeout", 180),
                cli_binaries={"claude": dict(path=str(CLAUDE), sha256=hashlib.sha256(CLAUDE.read_bytes()).hexdigest()),
                              "dcode": dict(path=str(DCODE), sha256=hashlib.sha256(DCODE.read_bytes()).hexdigest())},
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
    identity = container(work, profile, args.upstream / "data", args.image)
    try:
        commands = [[str(DCODE), "--version"], [str(CLAUDE), "--version"],
                    ["python3", "-c", "import numpy,pandas,scipy,pypdf; print('domain imports OK')"],
                    [str(DCODE), "--help"]]
        receipts = []
        for command in commands:
            output = subprocess.check_output(["docker", "exec", identity, *command], text=True, stderr=subprocess.STDOUT, timeout=60)
            receipts.append(dict(argv=command, stdout=output))
        write_json(checks / "checks.json", receipts)
    finally:
        stop_container(identity)
        subprocess.run(["docker", "rm", identity], check=True, capture_output=True)
    write_json(args.output / "preflight-ok.json", dict(paid_calls=0, plan_sha256=fingerprint(plan)))
    return selected, plan


def compact(report):
    return dict(task_id=report["task_id"], backend=report["backend"], status=report["status"],
                elapsed_seconds=report.get("cli", {}).get("elapsed_seconds"),
                fatal_provider_error=report.get("fatal_provider_error", False))


def safe_balance(key, root, name):
    try:
        value = balance(key)
        write_json(root / (name + ".json"), value)
        return value
    except Exception as error:
        write_json(root / (name + "-error.json"), dict(type=type(error).__name__, message=str(error)))
        return None


def monitor(root, stop, active, lock, done):
    markers = ("api error: 401", "api error: 402", "authentication_error", "insufficient balance", "invalid api key")
    while not done.wait(2):
        if stop.is_set():
            continue
        for path in root.glob("*/*/cli/*.log"):
            with path.open("rb") as stream:
                stream.seek(max(0, path.stat().st_size - 12000))
                text = stream.read().decode(errors="replace").lower()
            matched = next((m for m in markers if m in text), None)
            if matched:
                stop.set()
                write_json(root / "fatal-provider-error.json", dict(source=str(path.relative_to(root)), marker=matched,
                                                                    observed_at=now()))
                with lock:
                    owned = list(active)
                for identity in owned:
                    subprocess.run(["docker", "stop", "--time", "1", identity], capture_output=True)
                break
