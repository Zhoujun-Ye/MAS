"""Paired tests and intervals: McNemar, bootstrap CI, pass^k, oracle."""

from __future__ import annotations

import random
from math import comb


def mcnemar(base: dict[str, bool], other: dict[str, bool]) -> dict:
    """Exact two-sided McNemar test on tasks graded in both conditions."""
    common = sorted(set(base) & set(other))
    base_only = sum(base[key] and not other[key] for key in common)
    other_only = sum(other[key] and not base[key] for key in common)
    discordant = base_only + other_only
    tail = sum(comb(discordant, i) for i in range(min(base_only, other_only) + 1))
    p_value = min(1.0, 2 * tail / 2**discordant) if discordant else 1.0
    return {"n": len(common), "base_only": base_only, "other_only": other_only, "p_value": p_value}


def bootstrap_ci(values: list[float], *, samples: int = 10000, alpha: float = 0.05, seed: int = 0) -> tuple:
    """Percentile interval of the mean, resampling tasks with replacement."""
    if not values:
        return (None, None)
    rng = random.Random(seed)
    n = len(values)
    means = sorted(sum(rng.choices(values, k=n)) / n for _ in range(samples))
    low = means[int(alpha / 2 * samples)]
    high = means[min(samples - 1, int((1 - alpha / 2) * samples))]
    return (low, high)


def pass_hat_k(trials: dict[str, list[bool]], k: int) -> float | None:
    """τ² pass^k: mean over tasks of C(successes, k) / C(trials, k)."""
    scores = [comb(sum(outcomes), k) / comb(len(outcomes), k) for outcomes in trials.values() if len(outcomes) >= k]
    return sum(scores) / len(scores) if scores else None


def oracle(success: dict[str, dict[str, bool]], conditions: list[str]) -> dict:
    """Per-task best of ``conditions`` against the best single condition."""
    tasks = sorted(set.intersection(*(set(success[c]) for c in conditions)))
    if not tasks:
        return {"n": 0}
    rates = {c: sum(success[c][t] for t in tasks) / len(tasks) for c in conditions}
    best = max(rates, key=rates.get)
    oracle_rate = sum(any(success[c][t] for c in conditions) for t in tasks) / len(tasks)
    return {
        "n": len(tasks),
        "rates": rates,
        "best_single": best,
        "oracle": oracle_rate,
        "gain": oracle_rate - rates[best],
    }


def cohen_kappa(first: list[str], second: list[str]) -> float | None:
    """Agreement of two annotators on the same items."""
    if len(first) != len(second) or not first:
        return None
    n = len(first)
    observed = sum(a == b for a, b in zip(first, second)) / n
    labels = set(first) | set(second)
    expected = sum((first.count(label) / n) * (second.count(label) / n) for label in labels)
    return 1.0 if expected == 1 else (observed - expected) / (1 - expected)
