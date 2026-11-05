"""Shared Claude CLI environment, prompts, containers and evidence provenance."""

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import shlex
import stat
import subprocess
import urllib.request
import uuid
import time

from benchmarks._io import write_json
from harness._claude_hooks import BLOCKED_TOOLS

CLAUDE = Path("/home/zhoujunye/.local/bin/claude").resolve()

# Claude Code 2.1.286 has no TaskOutput tool; background agents notify the lead instead.
TOOLS = ("Bash", "Read", "Write", "Edit", "Glob", "Grep", "Agent", "Task", "SendMessage",
         "TaskCreate", "TaskUpdate", "TaskGet", "TaskList", "TaskStop")

THREADS = {name: "1" for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                                  "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")}

def backend_instructions(backend):
    if backend == "claude-code-single-agent":
        return ("This is the strict SINGLE-AGENT condition. Complete all work yourself. Native delegation "
                "is disabled by policy. Do not call task, spawn any subagent, or launch other model/agent "
                "processes through shell, Python, HTTP, or any other route. No external model calls.")
    if backend == "claude-code-subagents":
        # Current lead prompt, frozen by the user on 2026-11-04; keep text exact.
        return """Use Claude Code's native subagents as an orchestrator-worker team. You are the lead agent: analyze the task, plan how to answer it, delegate parts of the work to subagents with the native Agent tool, and synthesize their results into the final answer.

1. Scale delegation to the task's complexity. A focused task that one investigation can answer gets one subagent: treat it as a collaborator, doing some of the work yourself while it handles about half. A task with clearly distinct parts that can be worked on independently, or a hard question that benefits from different approaches, gets two to four subagents; use more only when there are many separable components. Prefer fewer, more capable subagents over many narrow ones, since each adds overhead. Always deploy at least one subagent.
2. Do the quick initial investigation needed for planning yourself, then deploy the subagents as soon as your plan is ready, launching independent ones together in parallel. Do not delegate trivial steps that you can complete yourself, and never delegate the final answer.
3. A subagent starts with a fresh context and sees only the description you write. Give each one a detailed, self-contained description: one core objective; the relevant background, including what you have already learned or ruled out; the task requirements and constraints that apply to its part; suggested starting points; the expected output format; and clear boundaries so that subagents do not overlap.
4. Scale each subagent's effort as well. State roughly how many tool calls its part warrants, about 3-10 for a simple lookup or check and 10-15 for a larger part, and ask it to stop and report as soon as it has the needed information or further tool use stops producing new relevant results.
5. Ask for a concise, information-dense report: the findings, the key evidence for them, and any conflicting or unresolved information for you to resolve.
6. Subagents run in the background, and you are notified automatically when each one finishes; do not sleep, poll, or check their status. Once you have delegated a part, do not also do it yourself. While they work, continue with your own part or analyze results that have arrived; if nothing else remains for you to do, end your turn and you will be resumed when their results arrive.
7. Think critically about each result. If important gaps or conflicts remain, deploy a focused follow-up subagent. When further work has diminishing returns, or the shared time or tool limits are running low, stop delegating. Before writing the final answer yourself, make sure every subagent you started has finished or been stopped."""
    raise ValueError("Unsupported backend: " + backend)


def limit_instructions(timeout, web_limit=0):
    """Condition-neutral run limits, stated identically to Single and Subagents."""
    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0:
        raise ValueError("Run limits require a positive integer timeout in seconds")
    if isinstance(web_limit, bool) or not isinstance(web_limit, int) or web_limit < 0:
        raise ValueError("Web request limit must be a non-negative integer")
    duration = f"{timeout} seconds" + (f" ({timeout // 60} minutes)" if timeout % 60 == 0 else "")
    text = f"Run limits: {duration} of wall-clock time in total"
    if web_limit:
        text += (f", and at most {web_limit} web search/fetch requests in total, shared by every agent and process "
                 "in this run (each web helper response reports how many remain)")
    return text + ". Do not try to work around tool limits or network restrictions.\n"

def organization_override(path, backend):
    if path is None:
        return None
    if backend != "claude-code-subagents":
        raise ValueError("Organization prompt overrides are only supported for Subagents studies")
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 32768:
        raise ValueError("Organization prompt must be a regular file of at most 32768 bytes")
    raw = path.read_bytes()
    text = raw.decode("utf-8").strip()
    if not text:
        raise ValueError("Organization prompt must not be empty")
    return dict(path=str(path.resolve()), sha256=hashlib.sha256(raw).hexdigest(), text=text)

def condition_instructions(args, backend):
    override = getattr(args, "organization_override", None)
    if override is not None:
        if backend != "claude-code-subagents":
            raise ValueError("Organization prompt overrides are only supported for Subagents studies")
        return override["text"]
    return backend_instructions(backend)

def now():
    return datetime.now(timezone.utc).isoformat()

def source_files():
    root = Path(__file__).resolve().parents[2]
    excluded = {"upstream", "assets", "__pycache__", "outputs", "archives", "build", "dist"}
    for parent, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in excluded
                         and not (Path(parent) / d).is_symlink())
        for name in sorted(names):
            path = Path(parent) / name
            if not name.startswith(".") and not path.is_symlink() and path.suffix in {".py", ".md", ".toml", ".sh", ".Dockerfile"}:
                yield path.relative_to(root), path

def source_manifest():
    return {str(relative): hashlib.sha256(path.read_bytes()).hexdigest() for relative, path in source_files()}

def credential(path, name="DEEPSEEK_API_KEY"):
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
    key = values.get(name)
    if not key:
        raise ValueError("Missing credential: " + name)
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

def options(backend):
    if backend not in {"claude-code-single-agent", "claude-code-subagents"}:
        raise ValueError("Only Claude Code conditions are active")
    tools = tuple(t for t in TOOLS if t not in BLOCKED_TOOLS) if backend == "claude-code-single-agent" else TOOLS
    return dict(model="deepseek-flash[1m]", allowed_tools=tools,
                disallowed_tools=("WebSearch", "WebFetch"), isolated_settings=True)

def native_env(backend, *, effort="max"):
    options(backend)
    if effort not in {"high", "max"}:
        raise ValueError("Study effort must be high or max")
    return dict(THREADS, HOME="/native/home",
                CLAUDE_CONFIG_DIR="/native/claude", ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic",
                ANTHROPIC_MODEL="deepseek-flash[1m]", ANTHROPIC_DEFAULT_OPUS_MODEL="deepseek-flash[1m]",
                ANTHROPIC_DEFAULT_SONNET_MODEL="deepseek-flash[1m]", ANTHROPIC_DEFAULT_HAIKU_MODEL="deepseek-flash",
                CLAUDE_CODE_SUBAGENT_MODEL="deepseek-flash[1m]", CLAUDE_CODE_EFFORT_LEVEL=effort,
                CLAUDE_CODE_AUTO_COMPACT_WINDOW="786432",
                CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS="0",
                CLAUDE_CODE_MAX_RETRIES="0",
                DISABLE_AUTOUPDATER="1", CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1",
                LANGSMITH_TRACING="false", LANGCHAIN_TRACING_V2="false")

class ContainerStartupError(RuntimeError):
    def __init__(self, identity, details):
        super().__init__("Startup failed for owned container " + identity)
        self.container_id = identity
        self.cleanup_details = details


def container(work, profile, dataset, image, key=None, network="bridge", backend="claude-code-subagents", *,
              dataset_mounts=None, environment_overrides=None, forwarded_env=(), gateway=None, effort="max"):
    if key and key != "offline-placeholder":
        raise RuntimeError("Paid containers are disabled pending credential isolation: never inject provider keys into solver environments")
    if forwarded_env:
        raise RuntimeError("Forwarding host credentials into solver containers is disabled")
    allowed_overrides = {"MAS_BENCHMARK_WEB", "MAS_WEB_LEDGER", "MAS_WEB_PROVIDER", "MAS_WEB_MAX_REQUESTS"}
    if set(environment_overrides or {}) - allowed_overrides:
        raise ValueError("Only benchmark web settings may override container environment")
    container_name = "mas-cli6-" + uuid.uuid4().hex[:12]
    environment = native_env(backend, effort=effort)
    environment.update(environment_overrides or {})
    if gateway is not None:
        from scripts.common.credential_gateway import CredentialGateway
        if not isinstance(gateway, CredentialGateway):
            raise TypeError("Expected a host credential gateway")
        environment.update(ANTHROPIC_BASE_URL=gateway.url + "/anthropic",
                           MAS_WEB_BASE_URL=gateway.url)
        # The Unix gateway is the only provider/web route, including shell tools.
        network = "none"
    args = ["docker", "run", "-d", "--pull", "never", "--name", container_name,
            "--label", "purpose=mas-information-cli6", "--network", network, "--cpus", "2",
            "--memory", "8g", "--pids-limit", "512", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--user", f"{os.getuid()}:{os.getgid()}",
            "--workdir", "/workspace"]
    mounts = [(work, "/workspace", False), (profile, "/native", False),
                                    (CLAUDE, str(CLAUDE), True),
                                    (Path(__file__).resolve().parents[2] / "harness/_claude_hooks.py", "/adapter-hooks.py", True)]
    mounts.extend(dataset_mounts if dataset_mounts is not None else [(dataset, "/data", True)])
    if gateway is not None and gateway.unix_path is not None:
        mounts += [(gateway.unix_path, "/host-gateway.sock", True),
                   (Path(__file__).with_name("gateway_bridge.py"), "/gateway-bridge.py", True)]
    for source, target, readonly in mounts:
        args += ["--mount", f"type=bind,src={source},dst={target}" + (",readonly" if readonly else "")]
    for variable, value in environment.items():
        args += ["--env", variable + "=" + value]
    for variable in forwarded_env:
        args += ["--env", variable]
    # Values are inherited through docker's environment, never placed in argv or receipts.
    args += ["--env", "ANTHROPIC_AUTH_TOKEN"]
    args += [image, "sleep", "infinity"]
    token = gateway.token if gateway is not None else "offline-placeholder"
    docker_env = {name: os.environ[name] for name in ("PATH", "HOME", "LANG") if name in os.environ}
    docker_env.update(ANTHROPIC_AUTH_TOKEN=token)
    # Persist ownership before Docker can create anything, including when its
    # client is interrupted before returning the assigned container ID.
    ownership = profile / "container-ownership.json"
    write_json(ownership, dict(container_name=container_name, status="creating"))
    identity = container_name
    try:
        identity = subprocess.check_output(args, env=docker_env, text=True, timeout=60).strip() or container_name
        write_json(ownership, dict(container_name=container_name, container_id=identity, status="created"))
        if gateway is not None and gateway.unix_path is not None:
            subprocess.run(["docker", "exec", "-d", identity, "python3", "/gateway-bridge.py"],
                           check=True, capture_output=True, timeout=10)
            deadline = time.monotonic() + 5
            while not (profile / "gateway-ready").exists():
                if time.monotonic() > deadline:
                    raise RuntimeError("Credential transport did not become ready")
                time.sleep(0.05)
    except BaseException as error:
        details = dict(stopped=False, removed=False, errors=[])
        try:
            stop_container(identity)
            details["stopped"] = True
        except Exception as cleanup_error:
            details["errors"].append(type(cleanup_error).__name__)
        finally:
            try:
                subprocess.run(["docker", "rm", "-f", identity], check=True, capture_output=True, timeout=15)
                details["removed"] = True
            except Exception as cleanup_error:
                details["errors"].append(type(cleanup_error).__name__)
        write_json(ownership, dict(container_name=container_name, container_id=identity,
                                  status="startup_failed", cleanup=details))
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            error.container_id, error.cleanup_details = identity, details
            raise
        raise ContainerStartupError(identity, details) from None
    return identity

def stop_container(identity):
    result = subprocess.run(["docker", "stop", "--time", "2", identity], capture_output=True, text=True, timeout=15)
    if result.returncode:
        raise RuntimeError("Could not stop owned container: " + identity)
    return dict(stopped=True, container_id=identity)

def safe_balance(key, root, name):
    try:
        value = balance(key)
        write_json(root / (name + ".json"), value)
        return value
    except Exception as error:
        write_json(root / (name + "-error.json"), dict(type=type(error).__name__,
                   http_status=getattr(error, "code", None)))
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
