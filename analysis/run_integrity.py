"""Read-only anomaly evidence, not authentication or semantic contribution proof."""

import json
from pathlib import Path


def rows(path):
    for index, line in enumerate(path.read_text(errors="replace").splitlines()):
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            yield index, value


def inspect_run(folder, backend):
    folder = Path(folder)
    profile = folder / "native-profile"
    codex = backend.startswith("codex-")
    ids, events = set(), []
    root_files = 0
    for path in sorted(profile.rglob("*.jsonl")):
        if path.is_symlink():
            continue
        records = list(rows(path))
        if codex:
            meta = next((r.get("payload", {}) for _, r in records if r.get("type") == "session_meta"), None)
            if meta is None:
                continue
            child = isinstance(meta.get("source"), dict) and "subagent" in meta["source"]
        else:
            if "observer" in path.relative_to(profile).parts:
                continue
            child = "subagents" in path.relative_to(profile).parts
        if not child:
            root_files += 1
        seen = set()
        for index, row in records:
            if codex and row.get("type") != "response_item":
                continue
            payload = row.get("payload", {}) if codex else row.get("message", {})
            if not isinstance(payload, dict):
                continue
            if payload.get("role") == "assistant" and isinstance(payload.get("id"), str):
                ids.add(payload["id"])
            if codex and row.get("type") == "response_item" and payload.get("type") in {"function_call", "custom_tool_call", "reasoning"} and isinstance(payload.get("id"), str):
                ids.add(payload["id"])
            # Response IDs are distinct from output item IDs in Codex rollouts.
            if isinstance(payload.get("response_id"), str):
                ids.add(payload["response_id"])
            if child:
                continue
            blocks = [payload] if codex else payload.get("content", [])
            if not isinstance(blocks, list):
                continue
            for b in blocks:
                if not isinstance(b, dict):
                    continue
                kind = b.get("type")
                name = b.get("name", "")
                call = kind in {"tool_use", "function_call", "custom_tool_call"}
                identity = b.get("call_id") or b.get("id")
                key = (kind, identity or json.dumps(b, sort_keys=True))
                if key in seen:
                    continue
                seen.add(key)
                events.append(dict(file=str(path.relative_to(profile)), line=index + 1,
                    timestamp=row.get("timestamp"), call=call, name=name,
                    delegate=call and (name in {"Agent", "Task"} or name.endswith("spawn_agent")),
                    background=bool((b.get("input") or {}).get("run_in_background"))
                        if isinstance(b.get("input", {}), dict) else False,
                    identity=identity, result_id=b.get("tool_use_id") or b.get("call_id"),
                    result=kind in {"tool_result", "function_call_output"},
                    worker_result=codex and payload.get("role") == "user"
                        and "Message Type: FINAL_ANSWER" in json.dumps(b),
                    text=json.dumps(b, ensure_ascii=False)))
    ledger = folder / "gateway-requests.jsonl"
    receipts = {}
    if ledger.exists():
        for _, row in rows(ledger):
            if row.get("route") in {"/responses", "/anthropic/v1/messages"}:
                receipts[row.get("request_id")] = row
    unmatched, unknown = [], []
    matched = 0
    for request, row in receipts.items():
        if not row.get("upstream_attempted"):
            continue
        identity = row.get("provider_response_id")
        if not identity:
            unknown.append(request)
        elif identity in ids or set(row.get("provider_output_ids", [])) & ids:
            matched += 1
        else:
            unmatched.append(dict(request_id=request, provider_response_id=identity))
    reconciliation = dict(status="review_required" if unmatched else
        "incomplete" if unknown or not receipts else "matched",
        matched_requests=matched, unmatched_requests=unmatched, unknown_response_requests=unknown,
        scope="Unmatched IDs flag possible out-of-transcript calls, not proven shell origin. Native helper calls, missing IDs/transcripts and same-UID tampering remain possible.")
    # Only a single lead transcript has an unambiguous local order without clocks.
    timeline = dict(status="unavailable", semantic_contribution="unverified")
    if root_files == 1:
        first = next((i for i, e in enumerate(events) if e["delegate"]), None)
        delegates = {e["identity"] for e in events if e["delegate"] and e["identity"]}
        background = {e["identity"] for e in events if e["delegate"] and e["background"]}
        result = next((i for i, e in enumerate(events) if e["worker_result"] or
            (not codex and e["result"] and e["result_id"] in delegates
             and e["result_id"] not in background)), None)
        answer = None
        submission = folder / "workspace/submission.json"
        if submission.is_file() and not submission.is_symlink():
            try:
                answer = json.loads(submission.read_text()).get("final_answer")
            except (ValueError, AttributeError):
                pass
        def window(end):
            selected = events[:end] if end is not None else events
            return dict(tool_calls=sum(e["call"] for e in selected),
                retained_blocks=len(selected), retained_characters=sum(len(e["text"]) for e in selected),
                answer_matches=[dict(file=e["file"], line=e["line"], timestamp=e["timestamp"])
                    for e in selected if isinstance(answer, str) and answer.strip()
                    and answer.strip() in e["text"] and not e["result"]])
        timeline.update(status="observed", first_delegation=first, first_delegation_result=result,
            before_first_delegation=window(first), before_first_delegation_result=window(result),
            scope="Lead transcript order; lexical answer matches are review flags, not semantic proof. Missing result means the window covers all retained work, not verified receipt.")
        timeline["answer_before_result_review_required"] = bool(
            timeline["before_first_delegation_result"]["answer_matches"])
    return dict(gateway_reconciliation=reconciliation, lead_delegation_timeline=timeline)
