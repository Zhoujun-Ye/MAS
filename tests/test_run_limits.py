from scripts.common.prompts.limits import limit_instructions
import threading
from types import SimpleNamespace

import pytest

from scripts.common.run import instructions, run_web_limit
from harness.runtime_support.runtime import (TOOLS, options)


def test_limit_text_states_time_and_shared_web_budget():
    assert limit_instructions(1200) == ("Run limits: 1200 seconds (20 minutes) of wall-clock time in total. "
                                        "Do not try to work around tool limits or network restrictions.\n")
    text = limit_instructions(1800, 4)
    assert text.startswith("Run limits: 1800 seconds (30 minutes) of wall-clock time in total, and at most 4 web")
    assert "shared by every agent and process in this run" in text and "how many remain" in text
    assert "(" not in limit_instructions(50).split("Do not")[0]
    for timeout, web in ((0, 0), (True, 0), (1.5, 0), (60, -1), (60, False)):
        with pytest.raises(ValueError):
            limit_instructions(timeout, web)


@pytest.mark.parametrize("benchmark,web", [("dataclawbench", False), ("hybriddeepresearch", True)])
def test_both_conditions_receive_identical_task_rules_and_limits(benchmark, web):
    task = SimpleNamespace(benchmark=benchmark, db="fixture", web=web)
    limits = dict(timeout=1800, web_limit=4 if web else 0)
    single = instructions(task, "claude-code-single-agent", **limits)
    subagents = instructions(task, "claude-code-subagents", **limits)
    shared = single.split("This is the strict SINGLE-AGENT condition.")[0]
    assert subagents.startswith(shared) and limit_instructions(**limits) in shared
    assert shared.index("Run limits") < shared.index("submission.json")


def test_web_limit_is_derived_once_and_rejected_for_offline_tasks():
    offline, online = SimpleNamespace(web=False), SimpleNamespace(web=True)
    assert run_web_limit(offline, SimpleNamespace(max_web_requests=9)) == 0
    assert run_web_limit(online, SimpleNamespace()) == 4
    assert run_web_limit(online, SimpleNamespace(max_web_requests=7)) == 7
    with pytest.raises(ValueError, match="web-enabled"):
        instructions(SimpleNamespace(benchmark="dataclawbench", db="x", web=False), "claude-code-subagents",
                     timeout=60, web_limit=2)


def test_removed_native_tool_is_not_requested():
    assert "TaskOutput" not in TOOLS
    for backend in ("claude-code-single-agent", "claude-code-subagents"):
        assert "TaskOutput" not in options(backend)["allowed_tools"]


def test_krama_prompt_states_limits_but_worker_files_stay_task_rules(tmp_path, monkeypatch):
    from benchmarks.kramabench.tasks import Task
    from scripts.kramabench import cli_runtime
    captured = {}

    class Gateway:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    class Adapter:
        def __init__(self, *args):
            pass
        def run(self, prompt, **kwargs):
            captured["prompt"] = prompt
            captured["rules"] = (kwargs["workspace"] / "CLAUDE.md").read_text()
            return dict(status="cli_exited")

    monkeypatch.setattr(cli_runtime, "CredentialGateway", Gateway)
    monkeypatch.setattr(cli_runtime, "ClaudeCodeSingleAgentCLI", Adapter)
    monkeypatch.setattr(cli_runtime, "container", lambda *a, **kw: "fixture-container")
    monkeypatch.setattr(cli_runtime, "stop_container", lambda *a: dict(stopped=True))
    monkeypatch.setattr(cli_runtime, "native_single_agent", lambda *a: dict(passed=True))
    monkeypatch.setattr(cli_runtime.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0))
    args = SimpleNamespace(output=tmp_path / "out", upstream=tmp_path, image="fixture", timeout=3600)
    cli_runtime.run_attempt(Task("probe", "astronomy", "Fixture"), "claude-code-single-agent", args,
                            "synthetic-secret", threading.Event(), set(), threading.Lock())
    assert cli_runtime.INSTRUCTIONS + limit_instructions(3600) in captured["prompt"]
    assert captured["rules"] == cli_runtime.INSTRUCTIONS
