import json
import threading
from datetime import datetime, timezone

import pytest

from harness import accounting
from harness.runner import bounded_jobs, write_json
from harness.trace import Trace, read_trace, validate

PRICING = {
    "models": {"m": {"cache_hit": 0.003, "cache_miss": 0.15, "output": 0.6}},
    "peak_multiplier": 2.0,
    "peak_hours_utc": [[1, 4], [6, 10]],
}


def test_write_json_creates_parents_and_atomically_replaces(tmp_path):
    path = tmp_path / "nested" / "record.json"
    write_json(path, {"revision": 1})
    assert json.loads(path.read_text()) == {"revision": 1}
    write_json(path, {"revision": 2})
    assert json.loads(path.read_text()) == {"revision": 2}
    assert not path.with_suffix(".json.tmp").exists()


@pytest.mark.parametrize("concurrency", [0, -1])
def test_bounded_jobs_rejects_nonpositive_concurrency(concurrency):
    with pytest.raises(ValueError, match="Concurrency must be positive"):
        list(bounded_jobs([], lambda x: x, concurrency, lambda result: False))


def test_bounded_jobs_does_not_dispatch_after_stop():
    stop = threading.Event()
    stop.set()
    started = []
    assert list(bounded_jobs(range(3), started.append, 1, lambda result: False, stop)) == []
    assert started == []


def test_bounded_jobs_stops_and_propagates_worker_exception():
    stop = threading.Event()
    started = []

    def worker(item):
        started.append(item)
        raise RuntimeError("worker failed")

    with pytest.raises(RuntimeError, match="worker failed"):
        list(bounded_jobs(range(3), worker, 1, lambda result: False, stop))
    assert stop.is_set()
    assert started == [0]


def test_peak_hours_and_cost():
    peak = datetime(2026, 10, 29, 7, 30, tzinfo=timezone.utc)  # Thursday 07:30 UTC
    weekend = datetime(2026, 10, 31, 7, 30, tzinfo=timezone.utc)
    assert accounting.is_peak(peak, PRICING) and not accounting.is_peak(weekend, PRICING)
    usage = {"cache_hit_tokens": 1_000_000, "cache_miss_tokens": 1_000_000, "completion_tokens": 1_000_000}
    assert accounting.call_cost("m", usage, weekend, PRICING) == pytest.approx(0.753)
    assert accounting.call_cost("m", usage, peak, PRICING) == pytest.approx(1.506)
    assert accounting.call_cost("unknown", usage, peak, PRICING) is None


def test_validate_flags_broken_logs(tmp_path):
    with Trace(tmp_path / "t.jsonl", "r") as trace:
        trace.emit("run_start")
        trace.emit("message", agent="a", idx=0, message={"role": "system", "content": "s"})
        call = {"id": "c1", "type": "function", "function": {"name": "search", "arguments": "{}"}}
        trace.emit("message", agent="a", idx=1, message={"role": "assistant", "content": "", "tool_calls": [call]})
        trace.emit("message", agent="a", idx=3, message={"role": "user", "content": "next"})
        trace.emit("llm_call", agent="a", context_len=9, usage={})
        trace.emit("boundary_msg", direction="down", content="task")
        trace.emit("run_end", status="completed")
    problems = validate(read_trace(tmp_path / "t.jsonl"))
    joined = "\n".join(problems)
    assert "completed without a final event" in joined
    assert "message index gap" in joined and "sent unlogged messages" in joined
    assert "without reasoning_content" in joined and "unanswered tool calls" in joined
    assert "without a reply" in joined


def test_usage_role_is_telemetry_only(tmp_path):
    from fakes import ScriptedClient
    from harness.agent import Agent
    requests = []
    for role in (None, "worker"):
        client = ScriptedClient(lambda *args: {"content": "done"})
        path = tmp_path / f"{role}.jsonl"
        with Trace(path, "cache") as trace:
            agent = Agent("specialist", client, trace, "Stable system", usage_role=role)
            agent.run("Stable public task", "Finish")
        requests.append(client.requests)
        event = next(e for e in read_trace(path) if e["type"] == "llm_call")
        assert event["usage_role"] == role
    assert requests[0] == requests[1]
