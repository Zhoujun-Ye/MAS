import pytest

from analysis import stats


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
