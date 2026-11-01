import pytest
from benchmarks.kramabench.evaluation import numeric_success


@pytest.mark.parametrize('predicted,target,expected', [
    (4, 4, 1), (4, 5, 0), ('4.0', 4, 1), (None, 4, 0),
    (100.005, 100.0, 1), (101.0, 100.0, 0), (1e-7, 0.0, 1), (1e-4, 0.0, 0),
    ('invalid', 4, 0), (float('nan'), 4, 0), (float('inf'), 4, 0), (True, 1, 0),
])
def test_numeric_branch(predicted, target, expected):
    assert numeric_success(predicted, target) == expected
