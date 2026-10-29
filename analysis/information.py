"""Information-level feedback grounded in decision-time transport receipts.

Receipts establish availability in a model input, not attention, truth or causal
use. Semantic annotations remain unknown until independently reviewed.
"""
import json
import re

from harness.trace import contexts


def observation_id(event):
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


def excerpt_checks(events, cutoff):
    """Compare claimed verbatim excerpts with earlier cited observations.

    A mismatch can be formatting or paraphrase, not necessarily a false fact.
    Exact matches establish text provenance only, never decision relevance.
    """
    evidence, aliases, checks = {}, {}, []

    def register(alias, key, fragments):
        aliases.setdefault(alias, {})[key] = fragments

    for event in events:
        if event["t"] > cutoff:
            continue
        if event["type"] == "evidence":
            key = event["evidence_id"]
            evidence[key] = event
            fragments = observed_fragments(event["text"])
            register(key, key, [event["text"]] + [text for _, text in fragments])
            for docid in {doc for doc, _ in fragments if doc is not None}:
                register(docid, key, [text for doc, text in fragments if doc == docid])
        if event["type"] == "tool_call":
            key = observation_id(event)
            if event.get("error") and key in evidence:
                evidence.pop(key)
                for alias in list(aliases):
                    aliases[alias].pop(key, None)
                    if not aliases[alias]:
                        del aliases[alias]
            if key in evidence:
                for alias in (event.get("call_id"), event.get("obs_id")):
                    if alias:
                        register(alias, key, aliases[key][key])
        if event["type"] != "peer_handoff" or event.get("form") != "structured":
            continue
        try:
            record = json.loads(event["payload"])
        except (ValueError, TypeError):
            continue
        if not isinstance(record, dict) or not isinstance(record.get("key_facts"), list):
            continue
        for index, fact in enumerate(record["key_facts"]):
            if not isinstance(fact, dict):
                continue
            source, quote = fact.get("source"), fact.get("verbatim")
            ids = re.findall(r"[\w-]+", source) if isinstance(source, str) else []
            ids = [key for key in ids if key.lower() not in {"docid", "tool", "call", "id", "source", "evidence"}]
            candidates = {}
            for alias in ids:
                for key, fragments in aliases.get(alias, {}).items():
                    candidates.setdefault(key, []).extend(fragments)
            matches = [key for key, fragments in candidates.items() if isinstance(quote, str) and quote.strip()
                       and any(quote in text for text in fragments)]
            checks.append(dict(message_id=event["message_id"], fact_index=index,
                               handoff_t=event["t"], cited_observation_events={k: evidence[k]["t"] for k in candidates},
                               cited_observation_owners={k: evidence[k].get("owner") for k in candidates},
                               unresolved_source_tokens=[k for k in ids if k not in aliases],
                               excerpt_check=("not_provided" if not isinstance(quote, str) or not quote.strip()
                                              else "source_unresolved" if not candidates
                                              else "exact_source_substring" if matches
                                              else "not_exact_source_substring"),
                               exact_excerpt_matches=matches, semantic_support=None))
    return checks


def decision_case(events, agent=None, call_t=None):
    final = next((e for e in reversed(events) if e["type"] == "final"), None)
    if agent is None:
        agent = final["agent"] if final else "leader"
    calls = [e for e in events if e["type"] == "llm_call" and e["agent"] == agent
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
        workers = {e.get("agent") for e in before if e["type"] == "agent_start" and e.get("usage_role") != "handoff"}
    deliveries = {e["message_id"]: e for e in before if e["type"] == "peer_delivery"}
    queued = {e["message_id"]: e for e in before if e["type"] == "peer_queued"}
    encoded = {e["message_id"]: e for e in before if e["type"] == "peer_handoff"}
    transport = []
    for key, event in queued.items():
        delivery, packet = deliveries.get(key), encoded.get(key)
        consumed = next((e for e in before if delivery and e["type"] == "llm_call"
                         and e["agent"] == delivery["recipient"] and e["t"] > delivery["t"]
                         and e["context_len"] >= delivery["context_len"]), None)
        transport.append(dict(message_id=key, sender=event["sender"], recipient=event["recipient"],
                              queued_t=event["t"], encoded_t=packet["t"] if packet else None,
                              delivered_t=delivery["t"] if delivery else None,
                              model_input_t=consumed["t"] if consumed else None,
                              requires_reply=event.get("requires_reply", False),
                              transport_status=("included_in_model_input" if consumed else
                                                "delivered_without_later_model_call" if delivery else
                                                "encoded_not_delivered" if packet else "queued_not_encoded"),
                              evidence_grants=packet.get("evidence_ids", []) if packet else [],
                              semantic_arrival=None, correct_use=None))
    reads = []
    for event in before:
        if event["type"] != "tool_call" or event.get("tool") not in ("read_evidence", "request_evidence"):
            continue
        # A successful response plus inclusion in a subsequent request is a read
        # receipt. Merely naming an id or attempting a denied read is not one.
        returned = []
        if event.get("communication") and not event.get("error") and not event.get("communication_limit"):
            if event["tool"] == "read_evidence":
                returned = [event["args"]["id"]]
            else:
                value = json.loads(event["observation"])
                returned = [r["id"] for r in value] if isinstance(value, list) else []
        message = next((e for e in before if e["type"] == "message" and e.get("agent") == event["agent"]
                        and e["message"].get("tool_call_id") == event.get("call_id")), None)
        consumed = next((e for e in before if message and e["type"] == "llm_call" and e["agent"] == event["agent"]
                         and e["t"] > message["t"] and e["context_len"] > message["idx"]), None)
        reads.append(dict(tool_event_t=event["t"], agent=event["agent"], returned_evidence_ids=returned,
                          model_input_t=consumed["t"] if consumed else None))
    return dict(decider=agent, decision_call_t=cutoff, decision_input=inputs,
                worker_contexts={k: v for k, v in history.items() if k in workers and k != agent},
                primary_evidence=source, transport=transport, reads=reads,
                excerpt_checks=excerpt_checks(events, cutoff),
                tool_failures=[e for e in before if e["type"] == "tool_call" and (e.get("error") or e.get("budget_exhausted"))],
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
