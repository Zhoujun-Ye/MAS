"""Native overflow must not masquerade as complete execution evidence."""

from concurrent.futures import ThreadPoolExecutor
import json

import pytest

from harness.evidence_mas.decision import DecisionProtocol
from harness.evidence_mas.hook import collect
from harness.evidence_mas.mcp import Server
from harness.evidence_mas.sharing import context_reply
from harness.evidence_mas.store import Store, StoreError


@pytest.fixture
def fixture(tmp_path):
    store = Store(tmp_path / 'native-profile/evidence', 'test')
    p = DecisionProtocol(store)
    p.initialize('Compute the fixture answer.')
    path = store.root.parent / 'claude/projects/-workspace/session/tool-results/overflow.txt'
    path.parent.mkdir(parents=True)
    text = 'progress\n' * 5000 + '{"answer":9}\n'
    path.write_text(text)
    event = dict(hook_event_name='PostToolUse', tool_name='Bash', tool_use_id='large',
        session_id='s', agent_id='worker', tool_input={'command':'python compute.py'},
        tool_response=dict(stdout='{"answer":1}\n', stderr='', interrupted=False,
            persistedOutputPath=str(path), persistedOutputSize=len(text.encode())))
    return store, p, path, text, event


def test_overflow_preview_is_not_a_complete_candidate_and_tail_is_readable(fixture):
    store, p, path, text, event = fixture
    context_reply(store, dict(hook_event_name='SessionStart', session_id='lead'), 'full')
    obs = collect(store, event)
    assert obs['completeness'] == 'pointer'
    assert obs['persisted_output_status'] == 'captured'
    assert store.read_blob(obs['output_ref']) == event['tool_response']
    assert store.read_blob(obs['persisted_output_ref']) == text
    assert not p.view()['candidates']
    assert p.check({'answer':1})['coverage'] is False
    update = context_reply(store, dict(hook_event_name='PostToolUse', session_id='lead'), 'full')
    item = json.loads(update['hookSpecificOutput']['additionalContext'].split('\n')[-1])['observations'][0]
    assert item['completeness'] == 'pointer' and item['persisted_output']['available']
    assert 'executed_results_preview' not in item
    server = Server(store, 'lead', 'lead', protocol='decision-v4')
    server.initialized = True
    reply = server.handle(dict(jsonrpc='2.0', id=1, method='tools/call', params=dict(
        name='obs_read', arguments=dict(obs_id=obs['id'], field='persisted_output', start=len(text)-20))))
    assert not reply['result']['isError']
    result = json.loads(reply['result']['content'][0]['text'])
    assert result['text'] == text[-20:] and result['total'] == len(text)
    path.unlink()
    assert collect(store, event) == obs
    assert store.call('obs.read',dict(obs_id=obs['id'],field='persisted_output',start=len(text)-20))['text'] == text[-20:]
    ro = Store(store.root, 'test', readonly=True)
    assert ro.call('obs.read',dict(obs_id=obs['id'],field='persisted_output',start=len(text)-20))['text'] == text[-20:]


@pytest.mark.parametrize('failure', ['missing','outside','symlink','parent_symlink','size','oversize','invalid_utf8','fifo'])
def test_unavailable_or_unsafe_overflow_remains_pointer_without_poisoning_store(fixture, failure):
    store, p, path, text, event = fixture
    output = event['tool_response']
    if failure == 'missing':
        path.unlink()
    elif failure == 'outside':
        output['persistedOutputPath'] = str(store.root.parent / 'private.txt')
    elif failure == 'symlink':
        path.unlink(); path.symlink_to(store.root / 'store.sqlite')
    elif failure == 'parent_symlink':
        path.parent.rename(path.parent.with_name('original'))
        path.parent.symlink_to(path.parent.with_name('original'), target_is_directory=True)
    elif failure == 'size':
        output['persistedOutputSize'] += 1
    elif failure == 'oversize':
        output['persistedOutputSize'] = 4 * 1024 * 1024 + 1
    elif failure == 'invalid_utf8':
        path.write_bytes(b'\xff'); output['persistedOutputSize'] = 1
    elif failure == 'fifo':
        import os
        path.unlink(); os.mkfifo(path)
    obs = collect(store, event)
    assert obs['completeness'] == 'pointer' and not obs['persisted_output_ref']
    assert not p.view()['candidates']
    with pytest.raises(StoreError, match='overflow unavailable'):
        store.call('obs.read',dict(obs_id=obs['id'],field='persisted_output'))
    collect(store, dict(event, tool_use_id='small',tool_response={'stdout':'{"answer":2}'}))
    assert p.check({'answer':2})['accepted']


def test_parallel_duplicate_overflow_hooks_preserve_one_snapshot(fixture):
    store, _, _, text, event = fixture
    pre = dict(event, hook_event_name='PreToolUse'); pre.pop('tool_response')
    with ThreadPoolExecutor(4) as pool:
        list(pool.map(lambda e:collect(store,e), [event,pre,event,pre]))
    with store.connect() as db:
        obs = store.latest(db,'observation')
    assert len(obs) == 1 and obs[0]['completeness'] == 'pointer'
    assert store.read_blob(obs[0]['persisted_output_ref']) == text


@pytest.mark.parametrize('flag', ['interrupted','truncated'])
def test_nested_native_flags_do_not_become_complete_success(fixture, flag):
    store, p, _, _, event = fixture
    event['tool_response'] = dict(stdout='{"answer":1}', **{flag:True})
    obs = collect(store,event)
    assert (obs['status']=='cancelled' if flag=='interrupted' else obs['completeness']=='truncated')
    assert not p.view()['candidates']


@pytest.mark.parametrize('field',['input','output','persisted_output'])
def test_read_limit_uses_same_bounded_span_as_end_through_mcp(fixture,field):
    store, _, _, _, event = fixture
    obs=collect(store,event)
    expected=store.call('obs.read',dict(obs_id=obs['id'],field=field,start=2,end=202))
    server=Server(store,'lead','lead',protocol='decision-v4');server.initialized=True
    response=server.handle(dict(jsonrpc='2.0',id=1,method='tools/call',params=dict(
        name='obs_read',arguments=dict(obs_id=obs['id'],field=field,start=2,limit=200))))
    assert not response['result']['isError']
    assert json.loads(response['result']['content'][0]['text'])==expected
    spec=next(t for t in server.handle(dict(jsonrpc='2.0',id=2,method='tools/list'))['result']['tools'] if t['name']=='obs_read')
    assert spec['inputSchema']['properties']['limit']['maximum']==16000


@pytest.mark.parametrize('args',[{'limit':0},{'limit':True},{'limit':16001},{'limit':2,'end':5}])
def test_read_limit_cannot_bypass_range_or_make_ambiguous_requests(fixture,args):
    store, _, _, _, event=fixture
    obs=collect(store,event)
    with pytest.raises(StoreError):store.call('obs.read',dict(obs_id=obs['id'],**args))
