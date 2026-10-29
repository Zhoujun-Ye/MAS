import json
import pytest

from harness.communication import full_snapshot, normalize_record, valid_record, parse_payload


def test_full_context_deduplicates_recursive_frames_without_dropping_facts():
    first = [{"role": "assistant", "content": "minimum nights 3", "reasoning_content": "exact reasoning"}]
    payload = {"intent": "verify", **full_snapshot(first)}
    for _ in range(8):
        messages = [{"role": "user", "content": json.dumps({"incoming_handoff": {
            "form": "full_context", "payload": payload}}, ensure_ascii=False)},
            {"role": "assistant", "content": "review"}]
        payload = {"intent": "verify", **full_snapshot(messages)}
    assert json.dumps(payload).count("minimum nights 3") == 1
    assert len(payload["frames"]) == 9
    assert first in payload["frames"].values()
    assert len(json.dumps(payload)) < 6000


def test_optional_null_does_not_discard_structured_facts():
    record = dict(conclusion="ok", key_facts=[dict(fact="minimum nights 3", source="e1", verbatim=None)],
                  ruled_out=[], open_questions=[], confidence="high")
    normalized = normalize_record(json.dumps(record))
    assert valid_record(normalized)
    assert json.loads(normalized)["key_facts"] == [dict(fact="minimum nights 3", source="e1")]


def test_fenced_json_and_ambiguous_candidates():
    assert parse_payload('Here is the record:\n```json\n{"fact":"3 nights"}\n```') == {"fact": "3 nights"}
    with pytest.raises(ValueError):
        parse_payload('```json\n{}\n```\n```json\n{}\n```')
    with pytest.raises(ValueError):
        parse_payload('Guess {"fact": "one"} or {"fact": "two"}')
