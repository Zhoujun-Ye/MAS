"""Offline, post-hoc archeology-hard-1 diagnostics; never a model-facing tool.

Run in the prepared analysis image with only the input directory mounted read-only.
No model client, evaluator or submitted pipeline is imported/executed.
"""

import argparse
from bisect import bisect_left
import hashlib
import json
import math
from pathlib import Path
from statistics import mean


def interval_means(points, start, end):
    """Compare estimands without dropping interior knots or reversing the interval."""
    points = sorted(points)
    lo, hi = sorted((start, end))
    xs = [x for x, _ in points]
    if (len(points) < 2 or any(not math.isfinite(v) for p in points for v in p)
            or not math.isfinite(lo) or not math.isfinite(hi)
            or len(set(xs)) != len(xs) or not xs[0] <= lo < hi <= xs[-1]):
        raise ValueError("Need finite unique samples and a nonempty in-range interval")

    def value(t):
        i = bisect_left(xs, t)
        if xs[i] == t:
            return points[i][1]
        (x0, y0), (x1, y1) = points[i - 1:i + 1]
        return y0 + (y1 - y0) * (t - x0) / (x1 - x0)

    knots = [(lo, value(lo)), *[(x, y) for x, y in points if lo < x < hi], (hi, value(hi))]
    area = sum((b - a) * (ya + yb) / 2 for (a, ya), (b, yb) in zip(knots, knots[1:]))
    samples = [y for x, y in points if lo <= x <= hi]
    inclusive = [value(t) for t in range(math.ceil(lo), math.floor(hi) + 1)]
    exclusive = [value(t) for t in range(math.ceil(lo), math.ceil(hi))]
    return {"endpoint_mean": mean([value(lo), value(hi)]),
            "time_weighted_mean": area / (hi - lo), "interior_knots": len(knots) - 2,
            "sample_mean": mean(samples) if samples else None,
            "integer_inclusive_mean": mean(inclusive) if inclusive else None,
            "integer_right_exclusive_mean": mean(exclusive) if exclusive else None}


def diagnose(dataset):
    import pandas as pd

    radio = pd.read_excel(dataset / "radiocarbon_database_regional.xlsx")
    climate = pd.read_excel(dataset / "climateMeasurements.xlsx", header=5)
    dates = radio.loc[radio.Region == "Malta", "date"]
    lo, hi = int(1950 - dates.max()), int(1950 - dates.min())
    core = climate[["Age_ky", "K"]].dropna()
    result = {"scope": "post_hoc_diagnostic_not_a_new_benchmark_score", "paid_calls": 0,
              "pandas_version": pd.__version__, "calendar_bounds": [lo, hi],
              "malta_rows": len(dates), "raw_age_means": interval_means(
                  [(1950 - age * 1000, k) for age, k in core.itertuples(index=False, name=None)], lo, hi),
              "input_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in sorted(dataset.glob("*.xlsx"))}}
    # Mirror the reviewed pinned reference's rounding, default tie ordering and
    # half-open annual range. Do not silently replace its conventions with ours.
    climate["year"] = 1950 - climate["Age_ky.1"].round(0) * 1000
    previous = climate[climate.year <= lo].sort_values("year", ascending=False).iloc[0]
    following = climate[climate.year >= hi].sort_values("year", ascending=True).iloc[0]
    assert previous.year <= lo < hi <= following.year
    assert not climate.year.between(lo, hi).any()
    annual = [previous.K + (t - previous.year) / (following.year - previous.year)
              * (following.K - previous.K) for t in range(lo, hi)]
    result["rounded_reference"] = {
        "mean": mean(annual), "years": len(annual),
        "brackets": [[float(row.year), float(row.K)] for row in (previous, following)],
        "tie_counts": [int((climate.year == row.year).sum()) for row in (previous, following)],
        "age_columns_equal": bool(climate["Age_ky"].equals(climate["Age_ky.1"]))}
    alternatives = {}
    for keep in ("first", "last"):
        unique = climate[["year", "K"]].dropna().drop_duplicates("year", keep=keep)
        alternatives[keep] = interval_means(list(unique.itertuples(index=False, name=None)), lo, hi)[
            "integer_right_exclusive_mean"]
    result["rounded_tie_policy_sensitivity"] = alternatives
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("/data"))
    args = parser.parse_args()
    print(json.dumps(diagnose(args.dataset), indent=2, allow_nan=False))
