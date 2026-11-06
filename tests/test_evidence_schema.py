from harness.evidence_mas.mcp import schema
from harness.evidence_mas.store import Store
from harness.evidence_mas.mcp import METHODS, Server, validate
import pytest


def test_version_references_are_explicit_and_not_freeform_objects():
    candidate = schema(Store.propose)['properties']
    for key in ('execution_ref', 'outcome_ref'):
        assert candidate[key]['required'] == ['id', 'revision']
        assert candidate[key]['additionalProperties'] is False
    assert candidate['depends_on']['items']['required'] == ['id', 'revision']
    assert 'candidate or selection' in candidate['depends_on']['description']


def test_source_and_selection_schemas_distinguish_ids_from_references():
    assert schema(Store.source)['properties']['source_type']['enum'] == ['task', 'codebook', 'document', 'data_manifest']
    selection = schema(Store.select)['properties']
    assert selection['considered_ids']['items'] == {'type': 'string'}
    assert selection['evidence_refs']['items']['required'] == ['id', 'revision']


@pytest.mark.parametrize('tool,args,path', [
    ('artifact_read', {'ref': {'id': 'source_x'}}, 'arguments.ref'),
    ('artifact_read', {'ref': {'id': 'source_x', 'revision': 1, 'kind': 'source'}}, 'arguments.ref'),
    ('source_register', {'source_type': 'file', 'content': 'x'}, 'arguments.source_type'),
    ('workspace_trace', {'object_id': 'obs_x', 'direction': 'forward'}, 'arguments.direction'),
    ('workspace_trace', {'object_id': 'obs_x', 'max_nodes': 201}, 'arguments.max_nodes'),
    ('artifact_read', {'ref': {'id': 'source_x', 'revision': True}}, 'arguments.ref.revision'),
    ('ledger_open_issue', {'question': 'q', 'analysis_scope': 'a', 'source_refs': ['source_x']}, 'arguments.source_refs[0]'),
])
def test_invalid_real_model_argument_patterns_are_actionable(tmp_path, tool, args, path):
    store = Store(tmp_path/'store', 'test')
    server = Server(store, 'lead', 'lead')
    server.handle(dict(jsonrpc='2.0', id=0, method='initialize'))
    reply = server.handle(dict(jsonrpc='2.0', id=1, method='tools/call', params={'name': tool, 'arguments': args}))
    assert reply['result']['isError']
    assert path in reply['result']['content'][0]['text']
    with store.connect() as db:
        assert store.latest(db) == []
    assert server.handle(dict(jsonrpc='2.0', id=2, method='ping'))['result'] == {}


def test_valid_references_and_null_optional_fields_validate():
    validate({'issue_id': 'issue_x', 'alternative': 'a', 'assumptions': [],
              'dependencies_complete': True,
              'execution_ref': None, 'depends_on': [{'id': 'selection_x', 'revision': 1}]},
             schema(Store.propose))
    validate({'ref': {'id': 'source_x', 'revision': 1}}, schema(Store.artifact_read))


def test_semantic_dependency_error_returns_recovery_guidance(tmp_path):
    store = Store(tmp_path/'store', 'test')
    source = store.call('source.register', {'source_type': 'document', 'content': 'Definition'})
    issue = store.call('ledger.open_issue', {'question': 'q', 'source_refs': [], 'analysis_scope': 'a'})
    server = Server(store, 'lead', 'lead')
    server.initialized = True
    reply = server.handle(dict(jsonrpc='2.0', id=1, method='tools/call', params={'name': 'ledger_propose',
        'arguments': {'issue_id': issue['id'], 'alternative': 'a', 'assumptions': [],
                      'dependencies_complete': True,
                      'depends_on': [{'id': source['id'], 'revision': 1}]}}))
    text = reply['result']['content'][0]['text']
    assert reply['result']['isError'] and 'candidate or selection' in text
    with store.connect() as db:
        assert store.latest(db, 'candidate') == []


def test_every_tool_has_closed_top_level_schema():
    for _, function in METHODS.values():
        spec = schema(function)
        assert spec['additionalProperties'] is False
