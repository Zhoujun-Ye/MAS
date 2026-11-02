"""Strict JSON decoding for model-produced structured output."""

import json


def strict_loads(raw, *, label):
    def invalid_constant(value):
        raise ValueError(f"Non-JSON value: {value}")

    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate {label} key: {key}")
            result[key] = value
        return result

    return json.loads(raw, parse_constant=invalid_constant, object_pairs_hook=unique_keys)
