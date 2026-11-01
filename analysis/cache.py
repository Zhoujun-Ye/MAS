"""Prompt-cache reuse measured from logged usage (DeepSeek disk cache).

DeepSeek persists a cache prefix unit at the end of each prompt and at the end
of each model output, and a request hits only units it matches completely. In
an append-only agent loop the next prompt is the previous prompt, plus the
previous output, plus new tool results. Each step between two calls of one
agent is classified by what its cache hit covered:

- ``prompt+output``: the previous prompt and output (verbatim passback works);
- ``prompt``: only the previous prompt (the output was not reused);
- ``partial``: less than the previous prompt (e.g. only a shared system prefix);
- ``miss``: nothing.

All rates are token-weighted (hit tokens / prompt tokens), never averages of
per-request percentages.
"""

from __future__ import annotations

# Cache units are coarse, so allow some tokens of slack when comparing lengths.
SLACK_TOKENS = 128
SLACK_SHARE = 0.02


def role(agent: str) -> str:
    return "worker" if agent.startswith("search_") else agent


def _covers(hit: int, length: int) -> bool:
    return hit >= length - max(SLACK_TOKENS, SLACK_SHARE * length)


def steps(events: list[dict]) -> list[dict]:
    """Every pair of consecutive LLM calls of the same agent, with what the hit covered."""
    calls: dict[str, list[dict]] = {}
    for event in events:
        if event["type"] == "llm_call" and event.get("usage_available", True):
            calls.setdefault(event["agent"], []).append(event)
    rows = []
    for agent, sequence in calls.items():
        for before, after in zip(sequence, sequence[1:]):
            prompt, output = before["usage"]["prompt_tokens"], before["usage"]["completion_tokens"]
            hit = after["usage"]["cache_hit_tokens"]
            if prompt <= 0 or after["usage"]["prompt_tokens"] <= 0:
                continue
            if _covers(hit, prompt + output):
                kind = "prompt+output"
            elif _covers(hit, prompt):
                kind = "prompt"
            else:
                kind = "partial" if hit else "miss"
            rows.append({"agent": agent, "role": after.get("usage_role") or role(agent), "kind": kind, "hit": hit, "reusable": prompt + output})
    return rows


def _bucket() -> dict:
    return {"calls": 0, "prompt_tokens": 0, "cache_hit_tokens": 0}


def _rate(bucket: dict) -> dict:
    rate = bucket["cache_hit_tokens"] / bucket["prompt_tokens"] if bucket["prompt_tokens"] else None
    return {**bucket, "hit_rate": rate}


def summarize(runs: list[tuple[str, list[dict]]]) -> dict:
    """``runs`` holds (condition, events) pairs; groups by condition, role and call position."""
    groups: dict[tuple, dict] = {}
    kinds: dict[tuple, dict[str, int]] = {}
    for condition, events in runs:
        seen: set[str] = set()
        for event in events:
            if event["type"] != "llm_call" or not event.get("usage_available", True):
                continue
            position = "later" if event["agent"] in seen else "first"
            seen.add(event["agent"])
            usage = event["usage"]
            for key in ((condition, "all", "all"), (condition, event.get("usage_role") or role(event["agent"]), position)):
                bucket = groups.setdefault(key, _bucket())
                bucket["calls"] += 1
                bucket["prompt_tokens"] += usage["prompt_tokens"]
                bucket["cache_hit_tokens"] += usage["cache_hit_tokens"]
        for row in steps(events):
            counts = kinds.setdefault((condition, row["role"]), {})
            counts[row["kind"]] = counts.get(row["kind"], 0) + 1
    return {
        "groups": [
            {"condition": c, "role": r, "position": p, **_rate(bucket)}
            for (c, r, p), bucket in sorted(groups.items())
        ],
        "steps": [{"condition": c, "role": r, **counts} for (c, r), counts in sorted(kinds.items())],
    }


def markdown(summary: dict) -> str:
    lines = [
        "| condition | role | position | calls | prompt tokens | hit tokens | hit rate |",
        "|---|---|---|---|---|---|---|",
    ]
    for g in summary["groups"]:
        rate = f"{g['hit_rate']:.1%}" if g["hit_rate"] is not None else "-"
        lines.append(
            f"| {g['condition']} | {g['role']} | {g['position']} | {g['calls']} | "
            f"{g['prompt_tokens']} | {g['cache_hit_tokens']} | {rate} |"
        )
    kinds = ("prompt+output", "prompt", "partial", "miss")
    lines += ["", "| condition | role | " + " | ".join(kinds) + " |", "|---|---|" + "---|" * len(kinds)]
    for s in summary["steps"]:
        lines.append(f"| {s['condition']} | {s['role']} | " + " | ".join(str(s.get(k, 0)) for k in kinds) + " |")
    return "\n".join(lines) + "\n"
