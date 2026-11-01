import json
import threading

import pytest

from fakes import ScriptedClient
from harness.agent import Observation, Tool
from harness.llm import ProviderError
from harness.subagents import LeaderSubagent, SubagentTemplate
from harness.trace import Trace


def test_fatal_drains_inflight_and_stops_queued_calls_and_tools(tmp_path):
    barrier = threading.Barrier(2)
    stopped = threading.Event()
    effects = []
    def policy(messages, tools, choice):
        if "delegate" in tools:
            return {"calls": [("delegate", {"template": "worker", "task": task})
                              for task in ("fatal", "inflight", "queued")]}
        task = json.loads(messages[-1]["content"])["task"]
        assert task != "queued"
        barrier.wait(timeout=5)
        if task == "fatal":
            raise ProviderError("http", "balance", 402)
        assert stopped.wait(timeout=5)
        return {"calls": [("write", {})]}
    tool = Tool("write", "Write", {"type": "object"},
                lambda *args: (effects.append(True) or Observation("written")), budgeted=True)
    with Trace(tmp_path / "trace.jsonl", "fatal") as trace:
        client = ScriptedClient(policy)
        session = LeaderSubagent(client, trace,
                                [SubagentTemplate("worker", "Work", "Worker", ("write",))], [tool], max_parallel=2)
        original_stop = session.session_budget.stop
        def stop(error):
            original_stop(error)
            stopped.set()
        session.session_budget.stop = stop
        with pytest.raises(ProviderError) as failure:
            session.run("task")
        result = failure.value.session_outcome
        assert result.infra_affected
        assert result.status == "incomplete"
        assert len(client.requests) == 3
        assert not effects
        assert all(status != "running" for status in result.child_statuses.values())
        assert list(result.child_statuses.values()).count("provider_error") == 1
        assert list(result.child_statuses.values()).count("stopped_after_fatal") == 1
