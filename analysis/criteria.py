"""Preregistered pass criteria (guide §7), fixed before any run.

Each proposition is checked per available evidence. Parts that need human
annotation or judge labels report ``pending`` until those exist, never pass.
"""

from __future__ import annotations

THRESHOLDS = {
    "p1_gap": 0.05,  # C1 below C0 by at least 5 points on some benchmark
    "p1_mas_specific": 0.10,  # or MAS-specific failures >= 10% of all tasks
    "p2_transmission_share": 0.40,  # of MAS-specific failures
    "p2_detector_precision": 0.80,  # against human labels
    "p2_c3_recovery": 0.50,  # C3 recovers at least half of the C1 gap
    "p3_top3_coverage": 0.70,  # of loss events
    "p3_kappa": 0.60,
    "p4_oracle_gain": 0.05,  # per-task oracle over best single form
}

TEXT = {
    "P1": "Some benchmark has C1 at least 5 points below C0, or MAS-specific failures (C0 right, C1 wrong) are at least 10% of tasks.",
    "P2": "At least 40% of MAS-specific failures are transmission loss with detector precision >= 0.8, and C3 recovers at least half of the C0-C1 gap.",
    "P3": "The three most common loss types cover at least 70% of loss events, with human kappa >= 0.6.",
    "P4": "The per-task oracle over C1-C4 beats the best single form by at least 5 points, and the best form differs across benchmarks or C3's context/cost is unacceptable.",
}


def _status(checks: list[bool | None]) -> str:
    if any(check is False for check in checks):
        return "fail"
    return "pass" if all(check is True for check in checks) else "pending"


def evaluate(benchmarks: dict[str, dict], human: dict | None = None) -> dict:
    """``benchmarks[name]`` holds the summary written by scripts/analyze.py."""
    human = human or {}
    t = THRESHOLDS
    p1 = []
    for summary in benchmarks.values():
        rates, paired = summary.get("success_rate", {}), summary.get("paired", {})
        if "C0" in rates and "C1" in rates:
            p1.append(rates["C0"] - rates["C1"] >= t["p1_gap"])
        if "C1" in paired:
            p1.append(paired["C1"]["base_only"] / max(1, paired["C1"]["n"]) >= t["p1_mas_specific"])
    p1_status = "pass" if any(p1) else ("fail" if p1 else "pending")

    p2 = []
    for summary in benchmarks.values():
        shares = summary.get("mas_specific_categories", {}).get("C1")
        if not shares or any(k.startswith("unresolved") for k in shares):
            p2.append(None)
        else:
            transmission = sum(v for k, v in shares.items() if k.startswith("transmission"))
            p2.append(transmission >= t["p2_transmission_share"])
        rates = summary.get("success_rate", {})
        if {"C0", "C1", "C3"} <= set(rates) and rates["C0"] > rates["C1"]:
            recovery = (rates["C3"] - rates["C1"]) / (rates["C0"] - rates["C1"])
            p2.append(recovery >= t["p2_c3_recovery"])
    precision = human.get("detector_precision")
    p2.append(None if precision is None else precision >= t["p2_detector_precision"])

    coverage, kappa = human.get("top3_loss_type_coverage"), human.get("kappa")
    p3 = [
        None if coverage is None else coverage >= t["p3_top3_coverage"],
        None if kappa is None else kappa >= t["p3_kappa"],
    ]

    oracles = [s["oracle"] for s in benchmarks.values() if s.get("oracle", {}).get("n")]
    differs = len({o["best_single"] for o in oracles}) > 1 if len(oracles) >= 2 else None
    c3_unacceptable = human.get("c3_unacceptable")  # judged from the context/cost tables
    if differs or c3_unacceptable:
        either = True
    elif differs is None or c3_unacceptable is None:
        either = None
    else:
        either = False
    p4 = [None if not oracles else max(o["gain"] for o in oracles) >= t["p4_oracle_gain"], either]
    return {
        "P1": {"status": p1_status, "criterion": TEXT["P1"]},
        "P2": {"status": _status(p2), "criterion": TEXT["P2"]},
        "P3": {"status": _status(p3), "criterion": TEXT["P3"]},
        "P4": {"status": _status(p4), "criterion": TEXT["P4"]},
        "thresholds": THRESHOLDS,
    }
