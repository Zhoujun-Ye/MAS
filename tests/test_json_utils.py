"""Shared decoding retains strictness and caller-specific diagnostics."""

import pytest

from benchmarks.kramabench.adapter import parse_submission
from harness.agent import parse_tool_arguments
from harness.json_utils import strict_loads


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
@pytest.mark.parametrize("decode", [parse_tool_arguments, parse_submission])
def test_non_json_constants_rejected_at_any_depth(decode, constant):
    with pytest.raises(ValueError, match="Non-JSON value"):
        decode('{"nested": [' + constant + ']}')


@pytest.mark.parametrize("decode,label", [(parse_tool_arguments, "argument"),
                                         (parse_submission, "submission")])
def test_nested_duplicate_keys_keep_caller_diagnostic(decode, label):
    with pytest.raises(ValueError, match=f"Duplicate {label} key: x"):
        decode('{"nested": {"x": 1, "x": 2}}')


def test_valid_json_and_empty_argument_compatibility():
    assert strict_loads('{"nested": [true, null, 1.5]}', label="fixture") == {
        "nested": [True, None, 1.5]}
    assert parse_tool_arguments("") == {}
    assert parse_tool_arguments(None) == {}
    with pytest.raises(ValueError):
        parse_submission("")
