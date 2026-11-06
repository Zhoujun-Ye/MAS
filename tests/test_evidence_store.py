import concurrent.futures
import json
import subprocess
import sys

import pytest

from harness.evidence_mas.store import Store, StoreError
from harness.evidence_mas.hook import collect
from harness.evidence_mas.mcp import Server


def ref(obj):
    return dict(id=obj['id'], revision=obj['revision'])


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / 'evidence', 'test-run')


def issue(store, question='Missing values?'):
    return store.call('ledger.open_issue', dict(question=question, source_refs=[], analysis_scope='filter'))


def candidate(store, item, **kwargs):
    return store.call('ledger.propose', dict(issue_id=item['id'], alternative='drop', assumptions=[],
                                            dependencies_complete=True, **kwargs))


def select(store, item, c, revision=0, **kwargs):
    return store.call('ledger.record_selection', dict(issue_id=item['id'], choice=ref(c) if c else None,
        rationale='Use documented semantics', considered_ids=[c['id']] if c else [], evidence_refs=[],
        expected_revision=revision, **kwargs), actor='lead', role='lead')


def view(store, item):
    return store.call('ledger.view', dict(issue_id=item['id']))


def observation(store, **kwargs):
    return store.call('obs.capture', dict(tool_name='Bash', tool_input={'command': 'fake'},
        tool_output='missing means unavailable', status='success', completeness='complete', **kwargs), role='collector')


def execution(store):
    source = store.call('source.register', dict(source_type='data_manifest', content='{"sha256":"fake_fixture_only"}'))
    return store.call('execution.register', dict(code='SELECT value FROM samples', parameters={}, inputs=[ref(source)]))


def evidence(store, target):
    obs = observation(store)
    return store.call('ledger.attach', dict(target_id=target['id'], relation='supports',
        claim='Same computation remains applicable', scope='applicability', limitation='fixture only', obs_id=obs['id']))


def test_observation_search_spans_and_hashes(store):
    first, second = observation(store), observation(store)
    assert first['id'] != second['id']
    assert first['output_hash'] == second['output_hash']
    result = store.call('obs.search', dict(query='UNAVAILABLE', limit=1))
    assert len(result['items']) == 1 and result['next_cursor'] == 1
    assert store.call('obs.read', dict(obs_id=first['id'], start=0, end=7))['text'] == 'missing'
    with pytest.raises(StoreError):
        store.call('obs.read', dict(obs_id=first['id'], start=-1))


def test_hook_pre_post_replay_and_no_recursion(store):
    event = dict(hook_event_name='PreToolUse', session_id='s', agent_id='a', tool_use_id='call1',
                 tool_name='Bash', tool_input={'command': 'fake'})
    before = collect(store, event)
    assert before['status'] == 'unknown'
    after = collect(store, dict(event, hook_event_name='PostToolUse', tool_response='done'))
    assert after['id'] == before['id'] and after['revision'] == 2
    assert collect(store, dict(event, hook_event_name='PostToolUse', tool_response='done')) == after
    assert collect(store, dict(event, tool_name='mcp__evidence__obs_read')) is None
    assert store.call('obs.list', {})['items'][0]['status'] == 'success'
    with store.connect() as db:
        assert store.get(db, before['id'], 1)['completeness'] == 'missing'


@pytest.mark.parametrize('interrupt,status', [(False, 'failed'), (True, 'cancelled')])
def test_failed_hook(store, interrupt, status):
    obj = collect(store, dict(hook_event_name='PostToolUseFailure', tool_name='Bash',
                             error='fixture failure', is_interrupt=interrupt))
    assert obj['status'] == status


def test_missing_output_and_permissions(store):
    with pytest.raises(StoreError):
        store.call('obs.capture', dict(tool_name='Read', tool_input={}))
    with pytest.raises(StoreError):
        store.call('obs.capture', dict(tool_name='Read', tool_input={}, completeness='complete'), role='collector')


def test_run_binding_and_path_safety(store, tmp_path):
    with pytest.raises(StoreError):
        Store(store.root, 'another-run')
    with pytest.raises(StoreError):
        store.call('obs.read', dict(obs_id='../other'))
    with pytest.raises(StoreError):
        store.read_blob('../other')
    link = tmp_path / 'linked'
    link.symlink_to(store.root)
    with pytest.raises(StoreError):
        Store(link, 'test-run')


def test_tampered_blob_detected(store):
    obs = observation(store)
    (store.blobs / obs['output_ref']).write_text('"tampered"')
    with pytest.raises(StoreError, match='integrity'):
        store.call('obs.read', dict(obs_id=obs['id']))


def test_unknown_and_unconfirmed_selection(store):
    item = issue(store)
    c = store.call('ledger.propose', dict(issue_id=item['id'], alternative='zero', assumptions=[]))
    assert c['freshness'] == 'unknown'
    with pytest.raises(StoreError):
        select(store, item, c)
    select(store, item, c, disclose_unconfirmed=True)
    assert view(store, item)['needs_review']


def test_multilevel_stale_and_unrelated_branch(store):
    a, b, c, d = [issue(store, str(i)) for i in range(4)]
    ca = candidate(store, a)
    sa = select(store, a, ca)
    cb = candidate(store, b, depends_on=[ref(sa)])
    sb = select(store, b, cb)
    cc = candidate(store, c, depends_on=[ref(sb)])
    select(store, c, cc)
    candidate(store, d)
    new_sa = select(store, a, ca, revision=1)
    assert new_sa['revision'] == 2
    assert view(store, b)['candidates'][0]['freshness'] == 'stale'
    assert view(store, c)['candidates'][0]['freshness'] == 'stale'
    assert view(store, c)['needs_review']
    assert view(store, d)['candidates'][0]['freshness'] == 'current'
    late = candidate(store, b, depends_on=[ref(sa)])
    assert late['freshness'] == 'stale'
    changed = store.call('ledger.revise_candidate', dict(candidate_id=cb['id'], expected_revision=1,
                        changes={'depends_on': [ref(new_sa)]}, rationale='Refresh assumption'))
    assert changed['freshness'] == 'current'
    assert view(store, c)['candidates'][0]['freshness'] == 'stale'


def test_withdrawal_and_unresolved_dependencies(store):
    a, b = issue(store), issue(store)
    ca = candidate(store, a)
    sa = select(store, a, ca)
    candidate(store, b, depends_on=[ref(sa)])
    unresolved = select(store, a, None, revision=1)
    assert view(store, b)['candidates'][0]['freshness'] == 'stale'
    assert candidate(store, b, depends_on=[ref(unresolved)])['freshness'] == 'unknown'


def test_candidate_cycle_rolls_back(store):
    a, b = issue(store), issue(store)
    ca = candidate(store, a)
    cb = candidate(store, b, depends_on=[ref(ca)])
    with pytest.raises(StoreError, match='Cycl'):
        store.call('ledger.revise_candidate', dict(candidate_id=ca['id'], expected_revision=1,
                        changes={'depends_on': [ref(cb)]}, rationale='Cycle'))
    assert view(store, a)['candidates'][0]['revision'] == 1


def test_selection_cycle_rolls_back(store):
    a, b = issue(store), issue(store)
    ca, cb = candidate(store, a), candidate(store, b)
    sa = select(store, a, ca)
    sb = select(store, b, cb)
    ca2 = store.call('ledger.revise_candidate', dict(candidate_id=ca['id'], expected_revision=1,
                    changes={'depends_on': [ref(sb)]}, rationale='Dependency'))
    select(store, a, ca2, revision=1)
    with pytest.raises(StoreError):
        store.call('ledger.revise_candidate', dict(candidate_id=cb['id'], expected_revision=1,
                    changes={'depends_on': [ref(sa)]}, rationale='Cycle'))


def test_execution_result_linkage_and_reconfirmation(store):
    item = issue(store)
    ex, other = execution(store), execution(store)
    obs = observation(store)
    out = store.call('outcome.register', dict(execution_ref=ref(ex), obs_id=obs['id'], result={'mean': 3}, status='success'))
    with pytest.raises(StoreError):
        candidate(store, item, execution_ref=ref(other), outcome_ref=ref(out))
    c = candidate(store, item, execution_ref=ref(ex), outcome_ref=ref(out))
    args = dict(candidate_id=c['id'], expected_revision=1, changes={}, rationale='Same input and computation')
    with pytest.raises(StoreError):
        store.call('ledger.revise_candidate', args)
    proof = evidence(store, c)
    updated = store.call('ledger.revise_candidate', dict(args, confirmation_evidence_ids=[proof['id']]))
    assert updated['revision'] == 2 and updated['outcome_ref'] == ref(out)
    assert 'SELECT' in store.call('artifact.read', dict(ref=ref(ex)))['text']


def test_failed_outcome_retained_and_not_success(store):
    ex = execution(store)
    obs = collect(store, dict(hook_event_name='PostToolUseFailure', tool_name='Bash', error='fixture'))
    with pytest.raises(StoreError):
        store.call('outcome.register', dict(execution_ref=ref(ex), obs_id=obs['id'], result=None, status='success'))
    obj = store.call('outcome.register', dict(execution_ref=ref(ex), obs_id=obs['id'], result=None, status='failed'))
    assert obj['status'] == 'failed'


def test_evidence_requires_provenance_and_marks_review(store):
    item = issue(store)
    c = candidate(store, item)
    select(store, item, c)
    evidence(store, c)
    assert view(store, item)['needs_review']
    select(store, item, c, revision=1)
    assert not view(store, item)['needs_review']
    with pytest.raises(StoreError):
        store.call('ledger.attach', dict(target_id=c['id'], relation='supports', claim='x', scope='y', limitation='z'))


def test_idempotent_operations(store):
    args = dict(question='q', source_refs=[], analysis_scope='s')
    first = store.call('ledger.open_issue', args, operation_id='op1')
    assert first == store.call('ledger.open_issue', args, operation_id='op1')
    with pytest.raises(StoreError):
        store.call('ledger.open_issue', dict(args, question='different'), operation_id='op1')


def test_concurrent_selections_exactly_one_wins(store):
    item = issue(store)
    c = candidate(store, item)
    select(store, item, c)
    def change(_):
        instance = Store(store.root, store.run_id)
        try:
            return select(instance, item, c, revision=1)['revision']
        except StoreError:
            return 'conflict'
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(change, range(4)))
    assert results.count(2) == 1 and results.count('conflict') == 3


def test_mcp_permissions_schema_and_invalid_input(store):
    server = Server(store, 'worker', 'worker')
    assert server.handle({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize'})['result']['protocolVersion']
    listing = server.handle({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'})['result']['tools']
    assert 'ledger_record_selection' not in [t['name'] for t in listing]
    bad = server.handle({'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
                         'params': {'name': 'obs_read', 'arguments': {'obs_id': '../escape'}}})
    assert bad['result']['isError']
    bad_type = server.handle({'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call',
                             'params': {'name': 'obs_read', 'arguments': {'obs_id': []}}})
    assert bad_type['result']['isError']
    assert 'arguments.obs_id' in bad_type['result']['content'][0]['text']


def test_mcp_real_stdio_and_hook_subprocess(tmp_path):
    root = tmp_path / 'store'
    command = [sys.executable, '-m', 'harness.evidence_mas.hook', '--root', str(root), '--run-id', 'fake-run']
    event = dict(hook_event_name='PostToolUse', tool_name='Bash', tool_response='fixture only')
    proc = subprocess.run(command, input=json.dumps(event), text=True, capture_output=True, timeout=10)
    assert proc.returncode == 0
    assert json.loads(proc.stdout) == {}
    requests = [dict(jsonrpc='2.0', id=1, method='initialize'),
                dict(jsonrpc='2.0', method='notifications/initialized'),
                dict(jsonrpc='2.0', id=2, method='tools/call', params=dict(name='obs_list', arguments={}))]
    command[2] = 'harness.evidence_mas.mcp'
    proc = subprocess.run(command, input='\n'.join(map(json.dumps, requests))+'\n', text=True, capture_output=True, timeout=10)
    assert proc.returncode == 0, proc.stderr
    replies = [json.loads(line) for line in proc.stdout.splitlines()]
    assert len(replies) == 2
    result = json.loads(replies[-1]['result']['content'][0]['text'])
    assert result['items'][0]['status'] == 'success'


def test_hook_failure_degraded_not_permission_change(tmp_path):
    root = tmp_path / 'store'
    command = [sys.executable, '-m', 'harness.evidence_mas.hook', '--root', str(root), '--run-id', 'fake-run']
    proc = subprocess.run(command, input='not-json', text=True, capture_output=True, timeout=10)
    assert proc.returncode == 0 and proc.stdout.strip() == '{}'
    assert json.loads((root / 'degraded.jsonl').read_text())['status'] == 'degraded'


@pytest.mark.parametrize('arguments', [dict(cursor=-1), dict(limit=0), dict(limit=True),
                                     dict(filters=[]), dict(filters={'private_path': '/etc/passwd'})])
def test_invalid_listing_arguments(store, arguments):
    with pytest.raises(StoreError):
        store.call('obs.list', arguments)


@pytest.mark.parametrize('changes', [dict(freshness='current'), dict(depends_on='wrong'),
                                   dict(dependencies_complete='yes'), dict(assumptions={}),
                                   dict(depends_on=[{'id': 'missing', 'revision': 1}])])
def test_invalid_candidate_revision_does_not_write(store, changes):
    item = issue(store)
    c = candidate(store, item)
    with pytest.raises(StoreError):
        store.call('ledger.revise_candidate', dict(candidate_id=c['id'], expected_revision=1,
                    changes=changes, rationale='bad'))
    assert view(store, item)['candidates'][0]['revision'] == 1


def test_source_evidence_history_and_read_audit(store):
    source = store.call('source.register', dict(source_type='codebook', content='Missing means unavailable.'))
    item = issue(store)
    c = candidate(store, item)
    link = store.call('ledger.attach', dict(target_id=c['id'], relation='contradicts', claim='Not zero',
        scope='meaning', limitation='Does not justify dropping', source_ref=ref(source), start=0, end=7))
    selection = select(store, item, c)
    select(store, item, c, revision=1)
    history = store.call('ledger.history', dict(object_id=selection['id'], limit=1))
    assert history['items'][0]['revision'] == 1 and history['next_cursor'] == 1
    assert link['source_ref'] == ref(source)
    with store.connect() as db:
        event = json.loads(db.execute('SELECT body FROM events ORDER BY seq DESC LIMIT 1').fetchone()[0])
        assert store.read_blob(event['arguments_ref'])['object_id'] == selection['id']


def test_new_execution_reconfirms_without_reusing_old_result(store):
    item = issue(store)
    ex = execution(store)
    obs = observation(store)
    out = store.call('outcome.register', dict(execution_ref=ref(ex), obs_id=obs['id'], result=3, status='success'))
    c = candidate(store, item, execution_ref=ref(ex), outcome_ref=ref(out))
    second = store.call('outcome.register', dict(execution_ref=ref(ex), obs_id=observation(store)['id'], result=3, status='success'))
    new = store.call('ledger.revise_candidate', dict(candidate_id=c['id'], expected_revision=1,
        changes={'outcome_ref': ref(second)}, rationale='New execution same numeric result'))
    assert new['outcome_ref'] != c['outcome_ref'] and new['freshness'] == 'current'


def test_configuration_is_pure_and_entrypoint_works_outside_repo(tmp_path):
    from harness.evidence_mas.config import fragments
    root = tmp_path / 'store'
    cfg = fragments(root, 'isolated-test', python=sys.executable)
    assert not root.exists()
    server = cfg['mcp']['mcpServers']['evidence']
    request = dict(jsonrpc='2.0', id=1, method='initialize')
    proc = subprocess.run([server['command'], *server['args']], input=json.dumps(request)+'\n',
                          cwd=tmp_path, capture_output=True, text=True, timeout=10)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)['result']['serverInfo']['name'] == 'evidence'


def test_separate_mcp_processes_share_store(tmp_path):
    from harness.evidence_mas.config import fragments
    cfg = fragments(tmp_path/'store', 'shared-run', python=sys.executable)
    command = cfg['mcp']['mcpServers']['evidence']
    argv = [command['command'], *command['args']]
    def write(index):
        requests = [dict(jsonrpc='2.0', id=0, method='initialize'),
            dict(jsonrpc='2.0', id=1, method='tools/call', params=dict(name='ledger_open_issue',
                arguments=dict(question=f'Issue {index}', source_refs=[], analysis_scope='fixture', operation_id=f'op{index}')))]
        return subprocess.run(argv, input='\n'.join(map(json.dumps, requests))+'\n',
                              cwd=tmp_path, capture_output=True, text=True, timeout=20)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(write, range(4)))
    for result in results:
        assert result.returncode == 0, result.stderr
        assert not json.loads(result.stdout.splitlines()[-1])['result']['isError']
    store = Store(tmp_path/'store', 'shared-run')
    with store.connect() as db:
        assert len(store.latest(db, 'issue')) == 4


def test_mcp_batch_and_malformed_request(store):
    server = Server(store, 'worker', 'worker')
    assert server.handle([])['error']['code'] == -32600
    replies = server.handle([dict(jsonrpc='2.0', id=1, method='initialize'),
                             dict(jsonrpc='2.0', method='notifications/initialized'),
                             dict(jsonrpc='2.0', id=2, method='ping')])
    assert len(replies) == 2


def test_foreign_reference_rejected(store, tmp_path):
    other = Store(tmp_path/'other', 'other')
    ex = execution(other)
    with pytest.raises(StoreError):
        candidate(store, issue(store), execution_ref=ref(ex))


def test_mcp_worker_cannot_override_role(store):
    server = Server(store, 'worker', 'worker')
    server.handle(dict(jsonrpc='2.0', id=1, method='initialize'))
    result = server.handle(dict(jsonrpc='2.0', id=2, method='tools/call',
        params=dict(name='ledger_open_issue', arguments=dict(question='q', source_refs=[], analysis_scope='x', role='lead'))))
    assert result['result']['isError']
    assert 'role' in result['result']['content'][0]['text']


def test_workspace_bidirectional_trace(store):
    item = issue(store)
    c = candidate(store, item)
    assert c['claim_status'] == 'hypothesis'
    link = evidence(store, c)
    assert view(store, item)['candidates'][0]['claim_status'] == 'evidence_linked'
    selection = select(store, item, c)
    graph = store.call('workspace.trace', dict(object_id=link['obs_id']))
    assert {n['kind'] for n in graph['nodes']} >= {'observation', 'evidence', 'candidate', 'issue', 'selection'}
    assert selection['id'] in {n['id'] for n in graph['nodes']}
    outbound = store.call('workspace.trace', dict(object_id=c['id'], direction='inbound'))
    assert link['id'] in {n['id'] for n in outbound['nodes']}
    assert store.call('workspace.trace', dict(object_id=c['id'], max_nodes=1))['truncated']


def test_withdrawal_preserves_original_observation(store):
    item = issue(store)
    c = candidate(store, item)
    proof = evidence(store, c)
    original = store.call('obs.read', dict(obs_id=proof['obs_id']))
    select(store, item, c)
    withdrawn = store.call('ledger.revise_candidate', dict(candidate_id=c['id'], expected_revision=1,
        changes={'disposition': 'withdrawn'}, rationale='Interpretation withdrawn'))
    assert withdrawn['freshness'] == 'stale' and view(store, item)['needs_review']
    store.call('ledger.retract_evidence', dict(evidence_id=proof['id'], expected_revision=1,
        rationale='Does not support the interpretation'))
    assert store.call('obs.read', dict(obs_id=proof['obs_id'])) == original
    with pytest.raises(StoreError):
        select(store, item, withdrawn, revision=1, disclose_unconfirmed=True)
    assert len(store.call('ledger.history', dict(object_id=proof['id']))['items']) == 2
