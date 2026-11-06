from concurrent.futures import ThreadPoolExecutor

import pytest

from harness.runtime_support.budget import RequestBudget


def test_reservations_are_atomic_and_unknown_calls_stay_reserved():
    budget = RequestBudget('.65')
    def reserve(i):
        try:
            budget.reserve(str(i), {'max_tokens': 8192}, '/anthropic/v1/messages')
            return True
        except ValueError:
            return False
    with ThreadPoolExecutor(8) as pool:
        assert sum(pool.map(reserve, range(8))) == 2
    assert budget.summary()['unknown'] == 2
    assert float(budget.summary()['reserved_or_peak_estimated_usd']) <= .65


def test_complete_usage_releases_unused_reservation_once():
    budget = RequestBudget('.4')
    budget.reserve('a', {'max_tokens': 8192}, '/anthropic/v1/messages')
    row = dict(request_id='a', outcome='response_complete', usage={'input_tokens': 100, 'output_tokens': 10})
    budget.settle(row)
    first = budget.summary()
    budget.settle(row)
    assert budget.summary() == first
    budget.reserve('b', {'max_tokens': 8192}, '/anthropic/v1/messages')


@pytest.mark.parametrize('payload,path', [({'max_tokens': 8193}, '/anthropic/v1/messages'),
    ({'max_tokens': 1}, '/responses'), ({'max_tokens': 1, 'tools': [{'type': 'web_search'}]}, '/anthropic/v1/messages')])
def test_budget_rejects_unbounded_requests(payload, path):
    with pytest.raises(ValueError):
        RequestBudget(2).reserve('a', payload, path)
