from scripts.common.prompts.conditions import backend_instructions, condition_instructions, organization_override
import json
from types import SimpleNamespace

import pytest

from harness.runtime_support.runtime import (balance_deltas, credential, native_env, options)
from scripts.kramabench.cli_runtime import submission
from analysis.native_evidence import read_evidence


def test_scope_and_no_secrets_in_native_plan():
    assert "Agent" not in options("claude-code-single-agent")["allowed_tools"]
    assert not any("KEY" in key or "TOKEN" in key for key in native_env("claude-code-subagents"))
    with pytest.raises(ValueError, match="Only Claude"):
        options("deepagents")
    assert options("claude-code-subagents")["model"] == "deepseek-flash[1m]"
    assert native_env("claude-code-subagents")["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] == "0"
    assert native_env("claude-code-subagents")["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] == "0"


@pytest.mark.parametrize("backend", ["claude-code-single-agent", "claude-code-subagents"])
def test_output_limit_uses_native_default(backend):
    assert "CLAUDE_CODE_MAX_OUTPUT_TOKENS" not in native_env(backend, effort="high")


def test_claude_container_has_no_retired_runtime_dependency(tmp_path, monkeypatch):
    from harness.runtime_support import runtime
    captured = {}
    def check(command, **kwargs):
        captured.update(command=command, environment=kwargs["env"])
        return "owned-test-container\n"
    monkeypatch.setattr(runtime.subprocess, "check_output", check)
    monkeypatch.setenv("TAVILY_API_KEY", "synthetic-unrelated-secret")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "synthetic-host-secret")
    assert runtime.container(tmp_path, tmp_path, tmp_path, "existing-image", backend="claude-code-subagents") == "owned-test-container"
    command = " ".join(captured["command"])
    assert "deepagents" not in command and "dcode" not in command
    assert "ANTHROPIC_AUTH_TOKEN" in captured["command"]
    assert "ANTHROPIC_API_KEY" not in captured["command"]
    assert "TAVILY_API_KEY" not in captured["environment"]
    assert "DEEPSEEK_API_KEY" not in captured["environment"]
    assert "synthetic-host-secret" not in json.dumps(captured)


def test_protected_credentials_are_not_shell_executed(tmp_path):
    path = tmp_path / "private.env"
    path.write_text("# example\nDEEPSEEK_API_KEY='literal;$(not-executed)'\n")
    path.chmod(0o600)
    assert credential(path) == "literal;$(not-executed)"
    path.chmod(0o644)
    with pytest.raises(ValueError, match="0600"):
        credential(path)


def test_submission_path_and_shape(tmp_path):
    payload = dict(answer=1, pipeline_path="pipeline.py", evidence="checked", unfinished=[])
    (tmp_path / "pipeline.py").write_text("print(1)")
    (tmp_path / "submission.json").write_text(json.dumps(payload))
    assert submission(tmp_path) == payload
    (tmp_path / "pipeline.py").unlink()
    (tmp_path / "pipeline.py").symlink_to("/etc/passwd")
    with pytest.raises(ValueError, match="Symlink"):
        submission(tmp_path)


def test_native_usage_deduplicates_claude_message_chunks_and_tools(tmp_path):
    path = tmp_path / "leader.jsonl"
    first = dict(role="assistant", id="m1", model="deepseek-flash",
                 usage=dict(input_tokens=100, cache_read_input_tokens=200, output_tokens=5),
                 content=[dict(type="tool_use", id="t1", name="TeamCreate", input={})])
    last = dict(first, usage=dict(input_tokens=100, cache_read_input_tokens=200, output_tokens=20),
                content=[dict(type="tool_use", id="t2", name="Agent", input={})])
    path.write_text("\n".join(json.dumps(dict(message=m)) for m in [first, last, last]))
    result = read_evidence(tmp_path, "claude-code")
    assert result["observed_totals"] == dict(input_tokens=300, output_tokens=20, cache_hit_tokens=200)
    assert result["tools"] == dict(TeamCreate=1, Agent=1)
    assert result["by_role"]["leader"]["token_weighted_cache_hit_rate"] == pytest.approx(2/3)
    assert result["estimated_usd_off_peak"] > 0


def test_missing_native_accounting_is_unknown(tmp_path):
    result = read_evidence(tmp_path, "claude-code")
    assert result["estimated_usd_off_peak"] is None
    assert result["observed_delegation_calls"] == 0


def test_non_usd_balances_are_not_silently_zero():
    def receipt(amount):
        return dict(response=dict(balance_infos=[dict(currency="CNY", total_balance=amount)]))
    assert balance_deltas(receipt("30.00"), receipt("23.90")) == {"CNY": "6.10"}


def test_organization_prompt_is_explicit_frozen_and_subagents_only(tmp_path):
    path = tmp_path / "prompt.md"
    path.write_text("  Judge the stated evidence only.\n")
    override = organization_override(path, "claude-code-subagents")
    assert override["text"] == "Judge the stated evidence only."
    assert len(override["sha256"]) == 64
    args = SimpleNamespace(organization_override=override)
    assert condition_instructions(args, "claude-code-subagents") == override["text"]
    assert condition_instructions(SimpleNamespace(), "claude-code-subagents") == backend_instructions("claude-code-subagents")
    with pytest.raises(ValueError, match="only supported"):
        organization_override(path, "claude-code-single-agent")
    with pytest.raises(ValueError, match="only supported"):
        condition_instructions(args, "claude-code-agent-team")
    path.write_text("Changed instruction")
    assert organization_override(path, "claude-code-subagents")["sha256"] != override["sha256"]


def test_organization_prompt_rejects_empty_and_nonregular(tmp_path):
    path = tmp_path / "prompt.md"
    path.write_text("\n")
    with pytest.raises(ValueError, match="empty"):
        organization_override(path, "claude-code-subagents")
    alias = tmp_path / "alias.md"
    alias.symlink_to(path)
    with pytest.raises(ValueError, match="regular"):
        organization_override(alias, "claude-code-subagents")
    assert organization_override(None, "claude-code-subagents") is None


@pytest.mark.parametrize("failure", [None, "container", "adapter", "cleanup"])
def test_krama_gateway_lifecycle_without_provider(tmp_path, monkeypatch, failure):
    import threading
    from benchmarks.kramabench.tasks import Task
    from scripts.kramabench import cli_runtime as krama
    state = {}
    key = "synthetic-host-secret"

    class Gateway:
        def __init__(self, supplied, **kwargs):
            assert supplied == key and kwargs["web_limit"] == 0
        def __enter__(self):
            state["open"] = True
            return self
        def __exit__(self, *args):
            state["closed"] = True

    def container(*args, **kwargs):
        assert len(args) == 4 and "key" not in kwargs
        assert isinstance(kwargs["gateway"], Gateway)
        if failure == "container":
            raise RuntimeError(key)
        return "fake-container"

    class Adapter:
        def __init__(self, *args):
            pass
        def run(self, *args, **kwargs):
            if failure == "adapter":
                raise RuntimeError(key)
            return dict(status="cli_exited")

    def cleanup(identity):
        if failure == "cleanup":
            raise RuntimeError(key)
        return dict(stopped=True)

    monkeypatch.setattr(krama, "CredentialGateway", Gateway)
    monkeypatch.setattr(krama, "container", container)
    monkeypatch.setattr(krama, "ClaudeCodeSingleAgentCLI", Adapter)
    monkeypatch.setattr(krama, "native_single_agent", lambda *a: dict(passed=True))
    monkeypatch.setattr(krama, "stop_container", cleanup)
    monkeypatch.setattr(krama.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0))
    args = SimpleNamespace(output=tmp_path / "outputs", upstream=tmp_path, image="fake", timeout=30)
    active = set()
    stop = threading.Event()
    result = krama.run_attempt(Task("probe", "astronomy", "Offline fixture"),
        "claude-code-single-agent", args, key, stop, active, threading.Lock())
    assert state == dict(open=True, closed=True)
    assert not active
    assert key not in json.dumps(result)
    assert result["status"] == ("cleanup_failed" if failure == "cleanup" else "launcher_error" if failure else "cli_exited")


def test_krama_fatal_monitor_ignores_transcript_text_and_uses_host_ledger(tmp_path, monkeypatch):
    import threading, time
    from harness.runtime_support import runtime
    folder = tmp_path / "task-1" / "claude-code-subagents"
    (folder / "cli").mkdir(parents=True)
    # Untrusted tool output may quote provider error wording; it must not stop the batch.
    (folder / "cli/stdout.log").write_text('{"result":"API Error: 401 authentication_error insufficient balance invalid api key"}\n')
    ledger = folder / "gateway-requests.jsonl"
    ledger.write_text(json.dumps(dict(event="finished", upstream_attempted=True,
                                      route="/anthropic/v1/messages", http_status=200)) + "\n")
    stopped = []
    monkeypatch.setattr(runtime.subprocess, "run", lambda argv, **kw: stopped.append(argv[-1]))
    stop, done, lock = threading.Event(), threading.Event(), threading.Lock()
    watcher = threading.Thread(target=runtime.monitor, args=(tmp_path, stop, {"owned-container"}, lock, done, 0.02))
    watcher.start()
    try:
        time.sleep(0.3)
        assert not stop.is_set() and not (tmp_path / "fatal-provider-error.json").exists()
        with ledger.open("a") as stream:
            stream.write(json.dumps(dict(event="finished", upstream_attempted=True,
                                         route="/anthropic/v1/messages", http_status=402)) + "\n")
        deadline = time.monotonic() + 5
        while not stop.is_set() and time.monotonic() < deadline:
            time.sleep(0.02)
    finally:
        done.set()
        watcher.join(5)
    assert stop.is_set() and stopped == ["owned-container"]
    fatal = json.loads((tmp_path / "fatal-provider-error.json").read_text())
    assert fatal["http_status"] == 402 and fatal["basis"] == "host_gateway_upstream_response"
