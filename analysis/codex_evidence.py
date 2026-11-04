"""Read retained native Codex rollouts; never schedule or repair agent work."""

import json
from collections import Counter
from pathlib import Path


def inspect(profile, *, single):
    sessions = []
    for path in sorted(Path(profile).rglob("rollout-*.jsonl")):
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        meta = next((r["payload"] for r in rows if r.get("type") == "session_meta"), {})
        if not meta:
            continue
        events = [r["payload"] for r in rows if r.get("type") == "event_msg"]
        terminal = [e.get("type") for e in events if e.get("type") in {"task_complete", "turn_aborted"}]
        usage = [e.get("info", {}).get("total_token_usage") for e in events
                 if e.get("type") == "token_count" and e.get("info")]
        calls = {}
        for index, row in enumerate(rows):
            payload = row.get("payload", {})
            if row.get("type") == "response_item" and payload.get("type") in {"function_call", "custom_tool_call"}:
                identity = payload.get("call_id") or payload.get("id") or (path.name, index)
                calls[identity] = payload.get("name", "unknown")
        tool_counts = dict(Counter(calls.values()))
        sessions.append(dict(id=meta.get("id"), child=isinstance(meta.get("source"), dict)
                             and "subagent" in meta["source"], complete=bool(terminal and terminal[-1] == "task_complete"),
                             usage=usage[-1] if usage else None, spawn_calls=sum(n.endswith("spawn_agent") for n in calls.values()),
                             tool_calls_observed=len(calls), tool_counts=tool_counts,
                             substantive_work_status="unverified"))
    children = [s for s in sessions if s["child"]]
    roots = [s for s in sessions if not s["child"]]
    passed = len(roots) == 1 and roots[0]["complete"]
    passed = passed and (not children and not roots[0]["spawn_calls"] if single else
                         bool(children) and all(s["complete"] for s in children))
    return dict(passed=bool(passed), subagent_starts=len(children),
                subagent_stops=sum(s["complete"] for s in children), sessions=sessions,
                structural_delegation_observed=bool(children),
                structural_delegation_complete=bool(children) and all(s["complete"] for s in children),
                substantive_work_status="unverified",
                delegation_evidence_scope="Native lifecycle and retained tool-call requests only; no semantic contribution or result incorporation verification",
                tool_count_scope="Deduplicated retained tool-call requests, not proof of successful execution; zero calls does not imply no useful reasoning",
                accounting_scope="Native per-session totals; cross-session aggregation not yet verified")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", required=True)
    parser.add_argument("--profile", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(inspect(args.profile / "codex", single=args.backend.endswith("single-agent"))))
