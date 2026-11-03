import pytest
from benchmarks.kramabench.evaluation import numeric_success


@pytest.mark.parametrize('predicted,target,expected', [
    (4, 4, 1), (4, 5, 0), ('4.0', 4, 1), (None, 4, 0),
    (100.005, 100.0, 1), (101.0, 100.0, 0), (1e-7, 0.0, 0), (1e-4, 0.0, 0),
    ('invalid', 4, 0), (float('nan'), 4, 0), (float('inf'), 4, 0), (True, 1, 0),
])
def test_numeric_branch(predicted, target, expected):
    assert numeric_success(predicted, target) == expected


@pytest.mark.parametrize('target', [4.638e-13, -4.638e-13, 1e-100, -1e-100, 0.1, 100.0, 1e100])
def test_numeric_comparison_is_scale_and_sign_aware(target):
    assert numeric_success(target, target) == 1
    assert numeric_success(target * 1.00005, target) == 1
    assert numeric_success(target * 1.001, target) == 0
    assert numeric_success(0, target) == 0
    assert numeric_success(-target, target) == 0


def test_tiny_reference_regression_and_explicit_legacy_policy():
    predicted, target = 5.107269247909184e-13, 4.638e-13
    assert numeric_success(predicted, target) == 0
    assert numeric_success(predicted, target, numeric_policy='upstream_v2') == 1
    assert numeric_success(0, target, numeric_policy='upstream_v2') == 1
    assert numeric_success(1e-7, 0, numeric_policy='upstream_v2') == 1
    with pytest.raises(ValueError, match='Unknown numeric policy'):
        numeric_success(1, 1, numeric_policy='invalid')
