import pytest

from harness.communication import parse_payload


def test_fenced_json_and_ambiguous_candidates():
    assert parse_payload('Here is the record:\n```json\n{"fact":"3 nights"}\n```') == {"fact": "3 nights"}
    with pytest.raises(ValueError):
        parse_payload('```json\n{}\n```\n```json\n{}\n```')
    with pytest.raises(ValueError):
        parse_payload('Guess {"fact": "one"} or {"fact": "two"}')
