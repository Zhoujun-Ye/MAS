import json
import subprocess
import sys

import pytest

from harness.evidence_mas.store import Store, StoreError
from harness.evidence_mas.hook import collect
from harness.evidence_mas.mcp import Server


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / 'evidence', 'test-run')


def observation(store, **kwargs):
    return store.call('obs.capture', dict(tool_name='Bash', tool_input={'command': 'fake'},
        tool_output='missing means unavailable', status='success', completeness='complete', **kwargs), role='collector')


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


def test_mcp_batch_and_malformed_request(store):
    server = Server(store, 'worker', 'worker')
    assert server.handle([])['error']['code'] == -32600
    replies = server.handle([dict(jsonrpc='2.0', id=1, method='initialize'),
                             dict(jsonrpc='2.0', method='notifications/initialized'),
                             dict(jsonrpc='2.0', id=2, method='ping')])
    assert len(replies) == 2
