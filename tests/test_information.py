import json

from analysis.information import attribution, decision_case, excerpt_checks


def test_attribution_requires_information_feedback_not_success():
    assert attribution({"success": False}) == "unknown"
    base = dict(reviewed=True, decision_relevant=True, source_correct=True, arrived_in_decision_input=False)
    assert attribution(dict(base, decision_relevant=False, shared=False)) == "unknown"
    assert attribution(dict(base, shared=False)) == "not_shared"
    assert attribution(dict(base, shared=True, handoff_faithful=False)) == "handoff_omission_or_distortion"
    assert attribution(dict(base, shared=True, reference_granted=True, evidence_read=False)) == "evidence_not_read"
    assert attribution(dict(base, arrived_in_decision_input=True, decision_correct=False)) == "reasoning_or_coordination_after_arrival"
    assert attribution(dict(base, arrived_in_decision_input=True, execution_failed=True)) == "tool_execution_failure"
    assert attribution(dict(base, task_specification_adequate=False)) == "task_or_evaluator_mismatch"


def test_decision_input_excludes_final_answer_late_delivery_and_encoder():
    events = [
        dict(t=0, type="agent_start", agent="leader", usage_role="leader"),
        dict(t=1, type="message", agent="leader", idx=0, message=dict(role="system", content="system")),
        dict(t=2, type="peer_queued", message_id="m1", sender="researcher", recipient="leader"),
        dict(t=3, type="peer_handoff", message_id="m1", evidence_ids=["e1"]),
        dict(t=4, type="message", agent="leader", idx=1, message=dict(role="user", content="summary and e1")),
        dict(t=5, type="peer_delivery", message_id="m1", recipient="leader", context_len=2),
        dict(t=6, type="message", agent="handoff_1", idx=0, message=dict(role="user", content="invented fact")),
        dict(t=7, type="llm_call", agent="leader", context_len=2),
        dict(t=8, type="message", agent="leader", idx=2, message=dict(role="assistant", content="invented fact in answer")),
        dict(t=9, type="final", agent="leader"),
        dict(t=10, type="evidence", evidence_id="late", text="late fact"),
    ]
    case = decision_case(events)
    assert case["transport"][0]["model_input_t"] == 7
    assert case["reads"] == []  # A granted reference is not a read.
    assert len(case["decision_input"]) == 2
    assert "handoff_1" not in case["worker_contexts"]
    assert case["primary_evidence"] == []
    assert case["semantic_attribution"] == "unknown"


def test_excerpt_checks_do_not_promote_citations_to_truth():
    facts = [dict(fact="correct", source="e1", verbatim="Suruchee"),
             dict(fact="distorted", source="e1; e2", verbatim="Surachee"),
             dict(fact="empty", source="e1", verbatim=""),
             dict(fact="future", source="e2", verbatim="Surachee")]
    events = [dict(t=1, type="evidence", evidence_id="e1", text="Name: Suruchee"),
              dict(t=2, type="peer_handoff", form="structured", message_id="m1",
                   payload=json.dumps(dict(key_facts=facts))),
              dict(t=3, type="evidence", evidence_id="e2", text="Surachee")]
    checks = excerpt_checks(events, cutoff=3)
    assert [c["excerpt_check"] for c in checks] == [
        "exact_source_substring", "not_exact_source_substring", "not_provided", "source_unresolved"]
    assert checks[1]["unresolved_source_tokens"] == ["e2"]
    assert all(c["semantic_support"] is None for c in checks)
    assert excerpt_checks(events, cutoff=1) == []
