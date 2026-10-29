import json
from datetime import datetime, timezone

import pytest

from harness import accounting
from harness.llm import ProviderError
from harness.runner import RunSpec, prepare_output, run_batch
from harness.trace import Trace, read_trace, validate

PRICING = {
    "models": {"m": {"cache_hit": 0.003, "cache_miss": 0.15, "output": 0.6}},
    "peak_multiplier": 2.0,
    "peak_hours_utc": [[1, 4], [6, 10]],
}


def test_runner_keeps_errors_apart_and_reruns_them(tmp_path):
    spec = RunSpec("bcp", "7", "C1", 0)
    prepare_output(tmp_path, {"setup": 1})
    with pytest.raises(RuntimeError):
        prepare_output(tmp_path, {"setup": 2})

    def failing(spec, trace):
        raise ProviderError("http_400", "missing reasoning_content", 400)

    assert run_batch([spec], failing, tmp_path, 1) == {"error": 1}
    result = json.loads((tmp_path / "results" / f"{spec.run_id}.json").read_text())
    assert result["error"]["http_status"] == 400 and not result["error"]["fatal"]

    def succeeding(spec, trace):
        trace.emit("final", agent="lead")
        return {"status": "completed"}

    assert run_batch([spec], succeeding, tmp_path, 1) == {"completed": 1}
    assert len(list((tmp_path / "traces" / "attempts").glob("*.jsonl"))) == 1
    assert run_batch([spec], succeeding, tmp_path, 1) == {}  # finished runs are kept


def test_context_overflow_is_incomplete_not_rerun(tmp_path):
    spec = RunSpec("bcp", "7", "C3", 0)

    def overflowing(spec, trace):
        raise ProviderError("context_length", "maximum context length exceeded", 400)

    assert run_batch([spec], overflowing, tmp_path, 1) == {"incomplete": 1}
    assert run_batch([spec], overflowing, tmp_path, 1) == {}


def test_fatal_provider_error_stops_the_batch(tmp_path):
    specs = [RunSpec("bcp", str(i), "C0", 0) for i in range(4)]

    def no_balance(spec, trace):
        raise ProviderError("http_402", "Insufficient Balance", 402)

    statuses = run_batch(specs, no_balance, tmp_path, 1)
    assert statuses == {"error": 1, "skipped": 3}


def test_run_ids_are_file_safe():
    assert RunSpec("bcp", "769", "C1", 0).run_id == "bcp_q769_C1_r0"
    run_id = RunSpec("telecom", "[mobile_data]airplane|on", "C0", 2).run_id
    assert run_id.startswith("telecom_qmobile-data-airplane-on-") and run_id.endswith("_C0_r2")


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
