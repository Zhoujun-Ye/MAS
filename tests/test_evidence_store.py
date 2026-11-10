import io
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


@pytest.mark.parametrize('mode,protocol,tool', [
    ('observations', 'observations-v1', 'obs_list'),
    ('full', 'decision-v4', 'decision_view'),
])
@pytest.mark.parametrize('audit_failure', [False, True])
def test_mcp_unexpected_tool_failure_keeps_stdio_alive(tmp_path, monkeypatch, mode, protocol, tool, audit_failure):
    from harness.evidence_mas import mcp
    from harness.evidence_mas.decision import DecisionProtocol

    store = Store(tmp_path / 'store', 'failure-test')
    server = Server(store, 'lead', 'lead', mode=mode, protocol=protocol)
    target, method = (Store, 'call') if tool == 'obs_list' else (DecisionProtocol, 'view')
    original = getattr(target, method)
    calls = []

    def fail_once(self, *args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            if audit_failure:
                def fail_audit_once(self, *args, **kwargs):
                    monkeypatch.setattr(Store, 'connect', connect)
                    raise RuntimeError('private audit error')
                monkeypatch.setattr(Store, 'connect', fail_audit_once)
            raise RuntimeError('private fixture credential must not appear')
        return original(self, *args, **kwargs)

    if protocol == 'decision-v4':
        DecisionProtocol(store).initialize('Offline fixture')
    monkeypatch.setattr(target, method, fail_once)
    connect = Store.connect
    monkeypatch.setattr(mcp, 'Server', lambda *args, **kwargs: server)
    requests = [dict(jsonrpc='2.0', id=1, method='initialize'),
                dict(jsonrpc='2.0', method='notifications/initialized'),
                dict(jsonrpc='2.0', id=2, method='tools/call', params=dict(name=tool)),
                dict(jsonrpc='2.0', id=3, method='tools/call', params=dict(name=tool)),
                dict(jsonrpc='2.0', id=4, method='ping')]
    monkeypatch.setattr(sys, 'argv', ['mcp', '--root', str(store.root), '--run-id', 'failure-test'])
    monkeypatch.setattr(sys, 'stdin', io.StringIO('not-json\n' + '\n'.join(map(json.dumps, requests)) + '\n'))
    output = io.StringIO()
    monkeypatch.setattr(sys, 'stdout', output)
    mcp.main()
    replies = [json.loads(line) for line in output.getvalue().splitlines()]
    assert [r['id'] for r in replies] == [None, 1, 2, 3, 4]
    assert replies[0]['error']['code'] == -32700
    assert replies[2]['result']['isError'] is True
    assert 'No automatic retry' in replies[2]['result']['content'][0]['text']
    assert replies[3]['result']['isError'] is False and replies[4]['result'] == {}
    assert len(calls) == 2
    assert 'private' not in output.getvalue()
    if not audit_failure:
        with store.connect() as db:
            errors = [json.loads(r[0]) for r in db.execute('SELECT body FROM events')
                      if json.loads(r[0])['method'] == 'workspace.error']
        assert len(errors) == 1 and 'private' not in json.dumps(errors)


def test_mcp_internal_error_keeps_batch_and_request_ids(store, monkeypatch):
    server = Server(store, 'lead', 'lead')
    server.initialized = True
    monkeypatch.setattr(server, 'available', lambda name: 1 / 0)
    replies = server.handle([dict(jsonrpc='2.0', id='listing', method='tools/list'),
                             dict(jsonrpc='2.0', id='alive', method='ping')])
    assert replies[0] == dict(jsonrpc='2.0', id='listing', error=dict(code=-32603, message='Internal error'))
    assert replies[1]['id'] == 'alive' and replies[1]['result'] == {}


@pytest.mark.parametrize('exception', [KeyboardInterrupt, SystemExit])
def test_mcp_does_not_swallow_process_shutdown(store, monkeypatch, exception):
    server = Server(store, 'lead', 'lead')
    server.initialized = True
    def stop(*args, **kwargs):
        raise exception()
    monkeypatch.setattr(store, 'call', stop)
    with pytest.raises(exception):
        server.handle(dict(jsonrpc='2.0', id=1, method='tools/call', params=dict(name='obs_list')))


def capture(store, **kwargs):
    return store.call('obs.capture', dict(tool_name='Bash',
        tool_input={'command': 'unique-sql-input'}, tool_output='answer',
        status='success', completeness='complete', **kwargs), role='collector')


def test_input_discovery_and_clamped_reads(store):
    obs = capture(store)
    rows = store.call('obs.search', {'query': 'unique-sql-input'})['items']
    assert rows[0]['id'] == obs['id']
    assert 'unique-sql-input' in rows[0]['input_summary']
    assert rows[0]['preview'] == 'answer'
    assert 'input_ref' not in rows[0]
    assert 'unique-sql-input' in store.call('obs.read', dict(obs_id=obs['id'], field='input'))['text']
    assert store.call('obs.read', dict(obs_id=obs['id'], end=90000))['text'] == 'answer'
    empty = store.call('obs.read', dict(obs_id=obs['id'], start=90000))
    assert empty['text'] == '' and empty['start'] == empty['end'] == 6
    for args in ({'start': -1}, {'start': True}, {'start': 3, 'end': 1}, {'field': 'bad'}):
        with pytest.raises(StoreError):
            store.call('obs.read', dict(obs_id=obs['id'], **args))


def test_capture_does_not_scan_objects_or_check_decision_cycles(store, monkeypatch):
    def forbidden(*args):
        raise AssertionError('Unnecessary graph scan')
    monkeypatch.setattr(store, 'latest', forbidden)
    obs = capture(store, session_id='s', agent_id='a', tool_call_id='t')
    assert capture(store, session_id='s', agent_id='a', tool_call_id='t')['id'] == obs['id']
    assert store.call('obs.read', {'obs_id': obs['id']})['text'] == 'answer'


def test_read_does_not_reserve_writer_lock(store, monkeypatch):
    obs = capture(store)
    original = store.output_text
    def read(value):
        with store.connect() as other:
            other.execute('PRAGMA busy_timeout=0')
            other.execute('BEGIN IMMEDIATE')
            other.rollback()
        return original(value)
    monkeypatch.setattr(store, 'output_text', read)
    assert store.call('obs.read', {'obs_id': obs['id']})['text'] == 'answer'
