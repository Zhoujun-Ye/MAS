"""Estimated API cost from logged token usage, and the provider account balance.

Estimates apply the configured price table (USD per million tokens, off-peak)
and multiply it in DeepSeek's weekday peak hours. They are for planning and
monitoring; the balance change recorded around a batch is the actual charge,
less any other use of the same key during that window.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import httpx

from .llm import ModelConfig


def is_peak(ts: datetime, pricing: dict) -> bool:
    """Weekday peak window in UTC; Chinese public holidays (off-peak) are not modelled."""
    ts = ts.astimezone(timezone.utc)
    return ts.weekday() < 5 and any(start <= ts.hour < end for start, end in pricing["peak_hours_utc"])


def call_cost(model: str, usage: dict, ts: datetime, pricing: dict) -> float | None:
    rates = pricing["models"].get(model)
    if rates is None:
        return None
    factor = pricing["peak_multiplier"] if is_peak(ts, pricing) else 1.0
    tokens = (
        usage["cache_hit_tokens"] * rates["cache_hit"]
        + usage["cache_miss_tokens"] * rates["cache_miss"]
        + usage["completion_tokens"] * rates["output"]
    )
    return factor * tokens / 1_000_000


def estimate(events: list[dict], pricing: dict) -> float | None:
    """Estimated USD of every LLM call in one trace; None if a model has no price."""
    total = 0.0
    for event in events:
        if event["type"] != "llm_call":
            continue
        cost = call_cost(event["model"], event["usage"], datetime.fromisoformat(event["ts"]), pricing)
        if cost is None:
            return None
        total += cost
    return total


def balance(cfg: ModelConfig) -> dict:
    """Account balance (DeepSeek ``GET /user/balance``); the key is never logged."""
    response = httpx.get(
        f"{cfg.base_url}/user/balance",
        headers={"Authorization": f"Bearer {os.environ[cfg.api_key_env]}"},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    return {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "is_available": data.get("is_available"),
        "balances": [
            {"currency": item.get("currency"), "total": item.get("total_balance")}
            for item in data.get("balance_infos", [])
        ],
    }


def observed_balance(cfg):
    try:
        return dict(status='recorded', **balance(cfg))
    except Exception as error:
        return dict(status='unavailable', error_type=type(error).__name__)


def report(events, pricing, before, after):
    from decimal import Decimal
    from .trace import usage_summary
    delta = {}
    if before.get('status') == after.get('status') == 'recorded':
        start = {b['currency']: Decimal(b['total']) for b in before['balances']}
        end = {b['currency']: Decimal(b['total']) for b in after['balances']}
        delta = {c: str(start[c] - end[c]) for c in start.keys() & end.keys()}
    return dict(usage=usage_summary(events), cost_usd_estimate=estimate(events, pricing),
                balance_before=before, balance_after=after, account_balance_delta=delta,
                balance_scope='Account-wide delta, not attributable run cost when the key is shared; may include unrelated activity.')
