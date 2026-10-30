import json
import threading

import pytest

from fakes import ScriptedClient
from harness import planning
from harness.pool import bind_permissions
from harness.trace import Trace, read_trace, validate


def reply():
    return json.dumps(dict(members=[
        dict(role="researcher", template="researcher", assignment="Read inventory and send exact quantities to solver."),
        dict(role="solver", template="solver", assignment="Compute feasibility from researcher evidence; report to leader."),
        dict(role="leader", template="leader", assignment="Coordinate and submit the supported decision."),
    ]))


def test_generic_leader_decomposes_without_domain_tools(tmp_path):
    def policy(messages, tools, choice):
        assert tools == [] and choice == "none"
        catalogue = json.loads(messages[-1]["content"])["roles"]
        assert catalogue["leader"]["tools"] == []
        assert catalogue["researcher"]["tools"] == ["inventory"]
        return dict(content=reply())
    client = ScriptedClient(policy)
    with Trace(tmp_path / "plan.jsonl", "plan") as trace:
        trace.emit("run_start")
        spec = planning.plan_team("Can we fulfill the order?", client, trace, {"inventory": "read"})
        trace.emit("run_end", status="completed")
    assert len(client.requests) == 1
    assert bind_permissions(spec, {"inventory": "read"})["leader"] == ()
    assert validate(read_trace(trace.path)) == []


@pytest.mark.parametrize("output", [
    dict(content="not json"), dict(content=reply(), finish="length"),
    dict(calls=[("inventory", {})]),
])
def test_invalid_plan_never_launches_workers_or_retries(tmp_path, output):
    client = ScriptedClient(lambda *args: output)
    with Trace(tmp_path / "bad.jsonl", "bad") as trace:
        with pytest.raises(ValueError):
            planning.plan_team("Order", client, trace, {"inventory": "read"})
    assert len(client.requests) == 1


def test_frozen_plan_reuse_and_configuration_changes(tmp_path, monkeypatch):
    from types import SimpleNamespace
    client = ScriptedClient(lambda *args: dict(content=reply()))
    client._http = SimpleNamespace(close=lambda: None)
    monkeypatch.setattr(planning, "ChatClient", lambda cfg: client)
    args = ("task", "Order", client.cfg, tmp_path, threading.Event(),
            {"models": {"scripted": {"cache_hit": 0, "cache_miss": 0, "output": 0}},
             "peak_hours_utc": [], "peak_multiplier": 1}, {"inventory": "read"})
    first = planning.frozen_plan(*args)
    assert planning.frozen_plan(*args) == first
    assert len(client.requests) == 1
    with pytest.raises(ValueError, match="configuration changed"):
        planning.frozen_plan(*args[:-1], {"inventory": "search"})
    assert len(client.requests) == 1


def test_failed_planning_attempt_is_not_silently_retried(tmp_path, monkeypatch):
    from types import SimpleNamespace
    client = ScriptedClient(lambda *args: dict(content="invalid"))
    client._http = SimpleNamespace(close=lambda: None)
    monkeypatch.setattr(planning, "ChatClient", lambda cfg: client)
    args = ("task", "Order", client.cfg, tmp_path, threading.Event(), {}, {})
    with pytest.raises(ValueError):
        planning.frozen_plan(*args)
    with pytest.raises(RuntimeError, match="Prior planning attempt"):
        planning.frozen_plan(*args)
    assert len(client.requests) == 1
