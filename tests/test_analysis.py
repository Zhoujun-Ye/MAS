import pytest

from analysis import cache, stats


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
