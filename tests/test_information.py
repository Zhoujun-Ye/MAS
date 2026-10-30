import json

from analysis.information import attribution, decision_case


def test_attribution_requires_information_feedback_not_success():
    assert attribution({"success": False}) == "unknown"
    base = dict(reviewed=True, decision_relevant=True, source_correct=True, arrived_in_decision_input=False)
    assert attribution(dict(base, decision_relevant=False, shared=False)) == "unknown"
    assert attribution(dict(base, shared=False)) == "not_shared"
    assert attribution(dict(base, shared=True, handoff_faithful=False)) == "handoff_omission_or_distortion"
    assert attribution(dict(base, shared=True, reference_granted=True, evidence_read=False)) == "evidence_not_read"
    assert attribution(dict(base, arrived_in_decision_input=True, decision_correct=False)) == "available_but_failure_unresolved"
    assert attribution(dict(base, arrived_in_decision_input=True, decision_correct=False,
                            decision_information_sufficient=True)) == "reasoning_or_coordination_after_arrival"
    assert attribution(dict(base, arrived_in_decision_input=True, execution_failed=True)) == "tool_execution_failure"
    assert attribution(dict(base, task_specification_adequate=False)) == "task_or_evaluator_mismatch"


def test_decision_input_excludes_final_answer_late_delivery_and_private_context():
    events = [
        dict(t=0, type="agent_start", agent="leader", usage_role="leader"),
        dict(t=1, type="message", agent="leader", idx=0, message=dict(role="system", content="system")),
        dict(t=2, type="peer_queued", message_id="m1", sender="researcher", recipient="leader"),
        dict(t=3, type="peer_handoff", message_id="m1", evidence_ids=["e1"]),
        dict(t=4, type="message", agent="leader", idx=1, message=dict(role="user", content="message and e1")),
        dict(t=5, type="peer_delivery", message_id="m1", recipient="leader", context_len=2),
        dict(t=6, type="message", agent="private_worker", idx=0, message=dict(role="user", content="invented fact")),
        dict(t=7, type="model_input", agent="leader", context_len=2),
        dict(t=8, type="message", agent="leader", idx=2, message=dict(role="assistant", content="invented fact in answer")),
        dict(t=9, type="final", agent="leader"),
        dict(t=10, type="evidence", evidence_id="late", text="late fact"),
    ]
    case = decision_case(events)
    assert case["transport"][0]["model_input_t"] == 7
    assert case["reads"] == []  # A granted reference is not a read.
    assert len(case["decision_input"]) == 2
    assert "private_worker" not in case["worker_contexts"]
    assert case["primary_evidence"] == []
    assert case["semantic_attribution"] == "unknown"


def test_artifact_reads_have_separate_receipts_and_denials_are_not_reads():
    events = [dict(t=0, type='agent_start', agent='leader', usage_role='leader')]
    for index, tool in enumerate(('read_artifact', 'read_artifact', 'read_artifact', 'read_artifact')):
        t = 1 + index * 3
        events.extend([
            dict(t=t, type='tool_call', agent='leader', tool=tool, call_id=str(index),
                 args=dict(id='a1'), communication=True, error=index == 3,
                 observation=json.dumps([dict(id='a1')])),
            dict(t=t+1, type='message', agent='leader', idx=index,
                 message=dict(role='tool', tool_call_id=str(index), content='result')),
            dict(t=t+2, type='model_input', agent='leader', context_len=index+1),
        ])
    reads = decision_case(events)['reads']
    assert [r['returned_artifact_ids'] for r in reads] == [['a1'], ['a1'], ['a1'], []]
    assert all(r['returned_evidence_ids'] == [] for r in reads)
    assert all(r['model_input_t'] is not None for r in reads)
