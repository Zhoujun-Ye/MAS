import pytest

from harness.evidence_mas.audit import check_workflow
from harness.evidence_mas.store import Store


def test_missing_trace_is_incomplete_without_fabricating_call(tmp_path):
    store = Store(tmp_path/'store', 'test')
    store.call('obs.list', {}, actor='lead', role='lead')
    check = check_workflow(store, {'lead': ['obs.list', 'workspace.trace']})
    assert not check['complete']
    assert check['missing'] == [{'role': 'lead', 'method': 'workspace.trace'}]
    assert check_workflow(store, {'lead': ['obs.list']})['complete']
    assert not check_workflow(store, {'worker': ['obs.list']})['complete']


def test_failed_calls_do_not_complete_workflow(tmp_path):
    store = Store(tmp_path/'store', 'test')
    with pytest.raises(ValueError):
        store.call('workspace.trace', {'object_id': 'missing'}, actor='lead', role='lead')
    assert not check_workflow(store, {'lead': ['workspace.trace']})['complete']


def test_misspelled_requirements_fail_instead_of_silently_passing(tmp_path):
    store = Store(tmp_path/'store', 'test')
    with pytest.raises(ValueError):
        check_workflow(store, {'lead': ['workspace.trcae']})
