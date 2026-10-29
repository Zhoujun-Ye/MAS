import json

import pytest

from analysis import cache, criteria, stats
from analysis.loss_judge import build_case, parse_label, render


def test_mcnemar_exact():
    base = {str(i): True for i in range(5)} | {"x": False}
    other = {str(i): False for i in range(5)} | {"x": False}
    result = stats.mcnemar(base, other)
    assert result == {"n": 6, "base_only": 5, "other_only": 0, "p_value": 0.0625}
    assert stats.mcnemar(base, base)["p_value"] == 1.0


def test_pass_hat_k_and_oracle():
    trials = {"a": [True, True, False], "b": [True, True, True]}
    assert stats.pass_hat_k(trials, 1) == pytest.approx((2 / 3 + 1) / 2)
    assert stats.pass_hat_k(trials, 3) == pytest.approx(0.5)
    success = {"C1": {"t1": True, "t2": False}, "C2": {"t1": False, "t2": True}}
    result = stats.oracle(success, ["C1", "C2"])
    assert result["oracle"] == 1.0 and result["gain"] == 0.5


def test_bootstrap_is_reproducible():
    values = [1.0, 0.0, 1.0, 1.0]
    assert stats.bootstrap_ci(values, seed=3) == stats.bootstrap_ci(values, seed=3)
    low, high = stats.bootstrap_ci(values)
    assert 0.0 <= low <= 0.75 <= high <= 1.0


def test_kappa():
    assert stats.cohen_kappa(["a", "b"], ["a", "b"]) == 1.0
    assert stats.cohen_kappa(["a", "a", "b", "b"], ["a", "b", "a", "b"]) == 0.0


def test_criteria_need_evidence_before_passing():
    summary = {"success_rate": {"C0": 0.6, "C1": 0.5, "C3": 0.58}, "paired": {}}
    verdict = criteria.evaluate({"bcp": summary})
    assert verdict["P1"]["status"] == "pass"
    assert verdict["P2"]["status"] == "pending"  # detector precision needs human labels
    assert verdict["P3"]["status"] == "pending"
    assert criteria.evaluate({})["P1"]["status"] == "pending"


def test_loss_judge_case_and_parse():
    events = [
        {"t": 0, "type": "message", "agent": "lead", "message": {"role": "system", "content": "sys"}},
        {"t": 1, "type": "message", "agent": "search_1", "message": {"role": "tool", "tool_call_id": "c", "content": "born 1950"}},
        {"t": 2, "type": "final", "agent": "lead"},
        {"t": 3, "type": "message", "agent": "lead", "message": {"role": "user", "content": "late"}},
    ]
    case = build_case(events, "Birth year 1950")
    assert "born 1950" in case["other_contexts"] and "late" not in case["decider_context"]
    assert render([{"role": "user", "content": "x" * 50}], 20).count("omitted") == 1
    label = parse_label('```json\n{"loss_type": "omission", "edge": "search_1->lead", "direction": "up"}\n```')
    assert label["loss_type"] == "omission"
    assert parse_label('{"loss_type": "unknown"}') is None


def call(agent, prompt, output, hit):
    usage = {"prompt_tokens": prompt, "completion_tokens": output, "cache_hit_tokens": hit}
    return {"type": "llm_call", "agent": agent, "usage": usage}


def test_cache_steps_and_rates():
    events = [
        call("lead", 2000, 500, 1024),
        call("lead", 3000, 400, 2500),  # covers the previous prompt and output
        call("lead", 4000, 300, 3000),  # covers only the previous prompt
        call("search_1", 1500, 200, 1024),
        call("search_1", 2000, 100, 0),
    ]
    kinds = [row["kind"] for row in cache.steps(events)]
    assert kinds == ["prompt+output", "prompt", "miss"]
    summary = cache.summarize([("C1", events)])
    overall = next(g for g in summary["groups"] if g["role"] == "all")
    assert overall["hit_rate"] == pytest.approx((1024 + 2500 + 3000 + 1024) / 12500)
    first = next(g for g in summary["groups"] if g["role"] == "worker" and g["position"] == "first")
    assert first["cache_hit_tokens"] == 1024
    assert "| C1 | lead | 1 | 1 | 0 | 0 |" in cache.markdown(summary)


def test_cache_groups_explicit_team_roles_not_agent_name_prefixes():
    events = [dict(call("transport_specialist", 1000, 50, 0), usage_role="worker"),
              dict(call("transport_specialist", 1500, 50, 1100), usage_role="worker"),
              dict(call("encoder_1", 1600, 50, 1200), usage_role="handoff")]
    summary = cache.summarize([("summary", events)])
    assert {g["role"] for g in summary["groups"]} == {"all", "worker", "handoff"}
    assert summary["steps"][0]["role"] == "worker"


def test_generic_analysis_retains_unknown_and_preserves_outputs(tmp_path):
    from scripts.analyze import load_runs, summarize
    from harness.trace import Trace
    (tmp_path / "results").mkdir()
    for key, status, success in [("done", "completed", True), ("unfinished", "incomplete", True),
                                 ("ungraded", "completed", None)]:
        (tmp_path / "results" / f"{key}.json").write_text(json.dumps(dict(run_id=key, condition="summary", status=status, success=success)))
        with Trace(tmp_path / "traces" / f"{key}.jsonl", key) as trace:
            trace.emit("run_start")
            trace.emit("final", agent="leader")
            trace.emit("run_end", status=status)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    runs, traces = load_runs(tmp_path)
    row = summarize(runs)["conditions"]["summary"]
    assert row["graded"] == 1 and row["ungraded"] == 2 and row["incomplete"] == 1
    assert row["success_rate"] == 1 and row["semantic_loss"] is None
    assert row["estimated_cost_usd"] is None
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
