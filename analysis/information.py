"""Information-level feedback grounded in decision-time transport receipts.

Receipts establish availability in a model input, not attention, truth or causal
use. Semantic annotations remain unknown until independently reviewed.
"""
import json

from harness.trace import contexts


def observation_id(event):
    if event.get('evidence_id'):
        return event['evidence_id']
    try:
        value = json.loads(event.get("observation", ""))
        return value.get("evidence_id") if isinstance(value, dict) else None
    except (ValueError, TypeError):
        return None


def observed_fragments(text):
    """Decode only recorded tool windows; never fetch or join document contents."""
    fragments = []

    def visit(value, docid=None):
        if isinstance(value, dict):
            docid = str(value["docid"]) if "docid" in value else docid
            if isinstance(value.get("text"), str):
                fragments.append((docid, value["text"]))
            for child in value.values():
                if isinstance(child, (dict, list)):
                    visit(child, docid)
        elif isinstance(value, list):
            for child in value:
                visit(child, docid)

    try:
        visit(json.loads(text))
    except (ValueError, TypeError):
        pass
    return fragments


def message_lifecycle(events, cutoff=None):
    """Operational receipts only. Consumed means request input, not understanding.

    Keep later receipts visible but label availability at the chosen decision.
    Monotonic durations are valid only inside this run/process.
    """
    rows = {}
    by_t = {event["t"]: event for event in events}
    stages = {"peer_queued": "sent", "peer_mailbox": "delivered", "peer_consumed": "consumed"}
    for event in events:
        stage = stages.get(event["type"])
        if stage is None:
            continue
        key = event["message_id"]
        row = rows.setdefault(key, dict(message_id=key, sender=event.get("sender"),
            receiver=event.get("recipient"), source_tool_call_ids=[],
            sent_at=None, delivered_at=None, consumed_at=None))
        if event.get("source_tool_call_ids") is not None:
            row["source_tool_call_ids"] = event["source_tool_call_ids"]
        row[stage + "_at"] = event.get("ts")
        row[stage + "_t"] = event["t"]
        row[stage + "_ns"] = event.get("monotonic_ns")
        if stage == "consumed":
            row["request_id"] = event["request_id"]
            row["consumption_receipt_t"] = event["t"]
            boundary = by_t[event["request_id"]]
            row["consumed_t"] = boundary["t"]
            row["consumed_at"] = boundary.get("ts")
            row["consumed_ns"] = boundary.get("monotonic_ns")
    for row in rows.values():
        for a, b in (("sent", "delivered"), ("delivered", "consumed")):
            start, end = row.get(a + "_ns"), row.get(b + "_ns")
            row[a + "_to_" + b + "_ns"] = end - start if start is not None and end is not None else None
        if cutoff is not None:
            arrived = lambda stage: row.get(stage + "_t", cutoff + 1) <= cutoff
            row["at_decision"] = ("in_model_input" if arrived("consumed") else
                "mailbox_waiting_for_next_step" if arrived("delivered") else
                "transport_pending" if arrived("sent") else "sent_after_decision")
    return list(rows.values())


def decision_case(events, agent=None, call_t=None):
    final = next((e for e in reversed(events) if e["type"] == "final"), None)
    if agent is None:
        members = next((e['control']['team']['members'] for e in events if e['type'] == 'team_spec'), [])
        workers = {m['role'] for m in members if m.get('template', m['role']) != 'leader'}
        last_worker = next((e['agent'] for e in reversed(events)
                            if e['type'] == 'model_input' and e['agent'] in workers), None)
        agent = last_worker or (final['agent'] if final else 'leader')
    calls = [e for e in events if e["type"] == "model_input" and e["agent"] == agent
             and (final is None or e["t"] < final["t"])]
    call = next((e for e in calls if e["t"] == call_t), None) if call_t is not None else (calls[-1] if calls else None)
    if call is None:
        raise ValueError("No recorded decision call for this agent")
    cutoff = call["t"]
    history = contexts(events, upto=cutoff)
    inputs = history.get(agent, [])[:call["context_len"]]
    before = [e for e in events if e["t"] <= cutoff]
    invalid_ids = {observation_id(e) for e in before if e["type"] == "tool_call" and e.get("error")}
    source = [e for e in before if e["type"] == "evidence" and e["evidence_id"] not in invalid_ids]
    selected = next((e["control"]["team"]["members"] for e in events if e["type"] == "team_spec"), [])
    workers = {m["role"] for m in selected}
    if not workers:
        workers = {e.get("agent") for e in before if e["type"] == "agent_start"}
    deliveries = {e["message_id"]: e for e in before if e["type"] == "peer_delivery"}
    queued = {e["message_id"]: e for e in before if e["type"] == "peer_queued"}
    packets = {e["message_id"]: e for e in before if e["type"] == "peer_handoff"}
    transport = []
    for key, event in queued.items():
        delivery, packet = deliveries.get(key), packets.get(key)
        consumed = next((e for e in before if delivery and e["type"] == "model_input"
                         and e["agent"] == delivery["recipient"] and e["t"] > delivery["t"]
                         and e["context_len"] >= delivery["context_len"]), None)
        transport.append(dict(message_id=key, sender=event["sender"], recipient=event["recipient"],
                              queued_t=event["t"], sent_t=packet["t"] if packet else None,
                              delivered_t=delivery["t"] if delivery else None,
                              model_input_t=consumed["t"] if consumed else None,
                              requires_reply=event.get("requires_reply", False),
                              transport_status=("included_in_model_input" if consumed else
                                                "delivered_without_later_model_call" if delivery else
                                                "sent_not_delivered" if packet else "queued_not_sent"),
                              evidence_grants=packet.get("evidence_ids", []) if packet else [],
                              requested_evidence_ids=event.get("evidence_ids", []),
                              requested_artifact_ids=event.get("artifact_ids", []),
                              verbatim_transport=packet.get("payload") == event.get("intent") if packet else None,
                              artifact_grants=packet.get("artifact_ids", []) if packet else [],
                              semantic_arrival=None, correct_use=None))
    reads = []
    for event in before:
        if event["type"] != "tool_call" or event.get("tool") not in (
                "read_evidence", "read_artifact"):
            continue
        # A successful response plus inclusion in a subsequent request is a read
        # receipt. Merely naming an id or attempting a denied read is not one.
        returned = []
        if event.get("communication") and not event.get("error") and not event.get("communication_limit"):
            if event["tool"] in ("read_evidence", "read_artifact", "recover_artifact"):
                returned = [event["args"]["id"]]
            else:
                value = json.loads(event["observation"])
                returned = [r["id"] for r in value] if isinstance(value, list) else []
        message = next((e for e in before if e["type"] == "message" and e.get("agent") == event["agent"]
                        and e["message"].get("tool_call_id") == event.get("call_id")), None)
        consumed = next((e for e in before if message and e["type"] == "model_input" and e["agent"] == event["agent"]
                         and e["t"] > message["t"] and e["context_len"] > message["idx"]), None)
        reads.append(dict(tool_event_t=event["t"], agent=event["agent"], tool=event["tool"],
                          returned_evidence_ids=[key for key in returned if key.startswith("e")],
                          returned_artifact_ids=[key for key in returned if key.startswith("a")],
                          model_input_t=consumed["t"] if consumed else None))
    protocol_kinds = {'submission_frozen', 'artifact_not_granted', 'evidence_not_granted',
                      'invalid_arguments', 'permission_denied', 'action_refused'}
    return dict(message_lifecycle=message_lifecycle(events, cutoff), decider=agent, decision_call_t=cutoff, decision_input=inputs,
                worker_contexts={k: v for k, v in history.items() if k in workers and k != agent},
                primary_evidence=source, transport=transport, reads=reads,
                tool_failures=[e for e in before if e["type"] == "tool_call" and e.get("error")
                               and e.get('error_kind') not in protocol_kinds],
                protocol_failures=[e for e in before if e['type'] == 'tool_call' and e.get('error_kind') in protocol_kinds],
                command_nonzero_outcomes=[e for e in before if e['type'] == 'tool_call'
                                         and e.get('exit_code') not in (None, 0) and not e.get('error')],
                resource_denials=[e for e in before if e['type'] == 'tool_call' and e.get('budget_exhausted')],
                resource_finalizations=[e for e in before if e["type"] == "finalization_start"],
                semantic_attribution="unknown", causal_attribution="not_tested")


def attribution(annotation):
    """Map reviewed information-level facts to a bottleneck, never from success.

    Caller must supply independently reviewed semantic judgments, with trace
    citations retained alongside the annotation. Missing values stay unknown.
    """
    if not annotation.get("reviewed") or annotation.get("decision_relevant") is not True:
        return "unknown"
    if annotation.get("task_specification_adequate") is False:
        return "task_or_evaluator_mismatch"
    if annotation.get("source_correct") is False:
        return "acquisition_or_source_error"
    if annotation.get("source_correct") is not True:
        return "unknown"
    if annotation.get("arrived_in_decision_input") is True:
        if annotation.get("execution_failed") is True:
            return "tool_execution_failure"
        if annotation.get("decision_correct") is False:
            if annotation.get("decision_information_sufficient") is True or annotation.get("fact_used_incorrectly") is True:
                return "reasoning_or_coordination_after_arrival"
            return "available_but_failure_unresolved"
        return "available_at_decision"
    if annotation.get("arrived_in_decision_input") is not False:
        return "unknown"
    if annotation.get("shared") is False:
        return "not_shared"
    if annotation.get("shared") is True and annotation.get("handoff_faithful") is False:
        return "handoff_omission_or_distortion"
    if annotation.get("reference_granted") is True and annotation.get("evidence_read") is False:
        return "evidence_not_read"
    if annotation.get("handoff_faithful") is True and annotation.get("delivery_consumed") is False:
        return "delivery_or_scheduling_failure"
    return "unknown"
