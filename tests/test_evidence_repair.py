"""Synthetic, benchmark-independent regressions for the active evidence protocol."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json

import pytest

from harness.evidence_mas.decision import DecisionProtocol, PROTOCOL
from harness.evidence_mas.hook import collect
from harness.evidence_mas.measurements import measurement
from harness.evidence_mas.mcp import Server
from harness.evidence_mas.sharing import context_reply, MAX_CHARS, MAX_ITEMS, pure_delay
from harness.evidence_mas.store import Store, StoreError

TARGET = dict(quantity='distance',statistic='sum',population='routes',period='not_applicable',unit='m',dataset='synthetic')


@pytest.fixture
def protocol(tmp_path):
    p = DecisionProtocol(Store(tmp_path/'store','synthetic'))
    p.initialize('Calculate total distance in m for the routes.')
    return p


def emit(p, value, call, agent='w', session='s', **extra):
    return collect(p.store,dict(hook_event_name='PostToolUse',tool_name='Bash',tool_use_id=call,
        agent_id=agent,session_id=session,tool_input={'command':'python compute.py'},
        tool_response={'stdout':json.dumps(value)},**extra))


def select(p, actor='lead'):
    view = p.view()
    return p.select(view['snapshot'],view['candidates'][0]['id'],
        {'task_quote':'total distance in m','criterion':'Definition, scope, units and executed method match'},
        {c['id']:'Different method or target' for c in view['candidates'][1:]},actor=actor)


def test_one_character_reads_do_not_unlock_selection(protocol):
    emit(protocol, {'answer': 1}, 'first')
    emit(protocol, {'answer': 2}, 'second')
    for candidate in protocol.view()['candidates']:
        for _ in range(3):
            protocol.read(candidate['id'], limit=1)
    with pytest.raises(StoreError, match='unread'):
        select(protocol)
    for candidate in protocol.view()['candidates']:
        protocol.read(candidate['id'])
    select(protocol)


def test_wait_notice_is_once_per_native_context(protocol):
    context_reply(protocol.store, event(kind='SessionStart'), 'full')
    delay = dict(event(), tool_name='Bash', tool_input={'command': 'sleep 30'})
    reply = context_reply(protocol.store, delay, 'full')
    assert 'completion notifications' in reply['hookSpecificOutput']['additionalContext']
    assert context_reply(protocol.store, delay, 'full') == {}


def event(agent=None,session='root',kind='PostToolUse'):
    return dict(hook_event_name=kind,session_id=session,agent_id=agent)


def delivered(reply):
    text = reply['hookSpecificOutput']['additionalContext']
    return json.loads(text.split('\n')[-1])['observations']


@pytest.mark.parametrize('mode',['full','observations'])
def test_context_delta_reaches_other_contexts_without_polling_or_echo(protocol,mode):
    store=protocol.store
    first=context_reply(store,event(kind='SessionStart'),mode)
    assert len(first['hookSpecificOutput']['additionalContext'])<=MAX_CHARS
    own=emit(protocol,{'answer':1},'own',agent='unknown',session='root')
    foreign=emit(protocol,measurement(2,TARGET,{},answer_target=True),'foreign')
    reply=context_reply(store,event(),mode)
    assert [x['observation']['id'] for x in delivered(reply)]==[foreign['id']]
    assert own['id'] not in json.dumps(reply)
    assert context_reply(store,event(),mode)=={}
    assert not context_reply(store,event(kind='PreToolUse'),mode)
    with store.connect() as db:
        calls=[json.loads(r[0]) for r in db.execute('SELECT body FROM events')]
    assert not any(c['method']=='obs.read' for c in calls)
    assert any(c['method']=='workspace.context' for c in calls)


def test_worker_identity_survives_native_session_change(protocol):
    store=protocol.store
    context_reply(store,event('w',kind='SubagentStart'),'full')
    emit(protocol,{'answer':1},'self',agent='w',session='child-session')
    other=emit(protocol,{'answer':2},'other',agent='v')
    reply=context_reply(store,event('w','child-session'),'full')
    assert [i['observation']['id'] for i in delivered(reply)]==[other['id']]


def test_bounded_backlog_is_not_lost_and_parallel_hooks_do_not_repeat(protocol):
    context_reply(protocol.store,event(),'observations')
    expected={emit(protocol,{'text':str(i)+'x'*9000},str(i))['id'] for i in range(11)}
    def read(_):return context_reply(protocol.store,event(),'observations')
    with ThreadPoolExecutor(4) as pool: replies=list(pool.map(read,range(8)))
    refs=[]
    for r in replies:
        if not r:continue
        assert len(r['hookSpecificOutput']['additionalContext'])<=MAX_CHARS
        values=delivered(r);assert len(values)<=MAX_ITEMS
        refs.extend(v['observation']['id'] for v in values)
    assert len(refs)==len(set(refs))==11 and set(refs)==expected


def test_answer_at_end_of_large_output_is_announced_without_promoting_hints(protocol):
    context_reply(protocol.store,event(),'full')
    collect(protocol.store,dict(hook_event_name='PostToolUse',tool_name='Bash',tool_use_id='late',
        agent_id='w',session_id='s',tool_input={'command':'python compute.py'},
        tool_response={'stdout':'\n'.join(['progress']*1000+['{"answer":7}'])}))
    item=delivered(context_reply(protocol.store,event(),'full'))[0]
    assert '"answers": [7]' in item['executed_results_preview']
    assert '"answer":7' not in item['output_preview']


def test_control_characters_cannot_overflow_delivery_budget(protocol):
    context_reply(protocol.store,event(),'observations')
    for i in range(4):emit(protocol,{'text':'\u0000\\\n'*10000},str(i))
    reply=context_reply(protocol.store,event(),'observations')
    assert len(reply['hookSpecificOutput']['additionalContext'])<=MAX_CHARS


def test_pending_outputs_unknown_recipients_and_other_runs_are_not_shared(protocol,tmp_path):
    context_reply(protocol.store,event(),'full')
    collect(protocol.store,dict(hook_event_name='PreToolUse',session_id='s',agent_id='w',
        tool_name='Bash',tool_use_id='pending'))
    assert context_reply(protocol.store,event(),'full')=={}
    assert context_reply(protocol.store,{},'full')=={}
    other=Store(tmp_path/'other','other')
    context_reply(other,event(),'full')
    emit(protocol,{'answer':2},'complete')
    assert context_reply(other,event(),'full')=={}


def test_conflicts_require_lead_candidate_evidence_not_worker_reads_or_previews(protocol):
    emit(protocol,{'answer':2},'a');emit(protocol,{'answer':3},'b')
    with pytest.raises(StoreError,match='unread'):select(protocol)
    for c in protocol.view()['candidates']:protocol.read(c['id'],role='worker',actor='worker')
    with pytest.raises(StoreError,match='unread'):select(protocol)
    for c in protocol.view()['candidates']:protocol.read(c['id'],actor='other-lead')
    with pytest.raises(StoreError,match='unread'):select(protocol)
    for c in protocol.view()['candidates']:protocol.read(c['id'])
    select(protocol)
    assert protocol.check({'answer':protocol.view()['candidates'][0]['value']})['accepted']


def test_read_pagination_exposes_full_execution_without_silent_truncation(protocol):
    emit(protocol,{'answer':2,'diagnostic':'x'*20000},'a')
    candidate=protocol.view()['candidates'][0]
    first=protocol.read(candidate['id'],limit=4000)
    assert first['next_start']==4000 and first['total']['output']>20000
    pages=[first['output']];start=first['next_start']
    while start is not None:
        page=protocol.read(candidate['id'],start=start,limit=4000)
        pages.append(page['output']);start=page['next_start']
    assert len(''.join(pages))==first['total']['output']
    with pytest.raises(StoreError):protocol.read(candidate['id'],start=-1)
    with pytest.raises(StoreError):protocol.read(candidate['id'],limit=16001)


def test_intermediate_contrasts_are_readable_but_never_automatic_answers(protocol):
    for i,v in enumerate((2,3)):
        emit(protocol,measurement(v,TARGET,{'missing':str(i)}),str(i))
    view=protocol.view()
    assert not view['candidates'] and len(view['contrasts'])==1
    group=view['contrasts'][0]
    assert group['differing_values']
    first=protocol.read(group_id=group['id'])
    assert first['next_source_cursor']==1
    second=protocol.read(group_id=group['id'],source_cursor=1)
    assert first['observation']!=second['observation']
    assert protocol.check({'answer':2})['reason']=='no_comparable_conflict'
    assert protocol.check({'answer':2})['coverage'] is False
    assert protocol.check({'answer':2})['semantic_validity']=='unverified'


def test_audit_counts_decision_evidence_access_not_just_obs_read(tmp_path):
    from harness.evidence_mas.integration import audit
    p=DecisionProtocol(Store(tmp_path/'native-profile/evidence','benchmark-evidence'))
    p.initialize('Calculate total distance in m for the routes.')
    emit(p,{'answer':2},'a')
    events=tmp_path/'native-profile/observer/events.jsonl';events.parent.mkdir()
    events.write_text('\n'.join(json.dumps(dict(hook_event_name=k,agent_id='w')) for k in ('SubagentStart','SubagentStop')))
    server=Server(p.store,'lead','lead',protocol=PROTOCOL);server.initialized=True
    server.handle(dict(jsonrpc='2.0',id=1,method='tools/call',params=dict(name='decision_read',
        arguments={'candidate_id':p.view()['candidates'][0]['id']})))
    assert audit(tmp_path,'full')['delegation']['lead_reads_worker']


def test_same_value_new_assumptions_invalidate_review_not_duplicate_votes(protocol):
    emit(protocol,measurement(2,TARGET,{'policy':'a'},answer_target=True),'a')
    emit(protocol,measurement(3,TARGET,{'policy':'b'},answer_target=True),'b')
    for c in protocol.view()['candidates']:protocol.read(c['id'])
    select(protocol);before=protocol.view()['snapshot']
    emit(protocol,measurement(2,TARGET,{'policy':'a'},answer_target=True),'duplicate')
    assert protocol.view()['snapshot']==before
    emit(protocol,measurement(2,TARGET,{'policy':'changed'},answer_target=True),'changed')
    assert protocol.view()['snapshot']!=before
    assert protocol.check({'answer':2})['reason']=='selection_stale'
    with pytest.raises(StoreError,match='unread'):select(protocol)


def test_current_retained_v3_is_readonly_not_a_launch_fallback(protocol):
    emit(protocol,{'answer':2},'a')
    with protocol.store.connect() as db:db.execute("UPDATE meta SET value='decision-v3' WHERE key='decision_protocol'")
    ro=DecisionProtocol(Store(protocol.store.root,'synthetic',readonly=True))
    before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in protocol.store.root.rglob('*') if p.is_file()}
    assert ro.check({'answer':2})['accepted']
    ro.read(ro.view()['candidates'][0]['id'])
    assert before=={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in protocol.store.root.rglob('*') if p.is_file()}
    with pytest.raises(StoreError):protocol.initialize('Calculate total distance in m for the routes.')


def test_mcp_failed_selection_is_audited_and_worker_cannot_spoof_role(protocol):
    emit(protocol,{'answer':2},'a');emit(protocol,{'answer':3},'b')
    server=Server(protocol.store,'lead','lead',protocol=PROTOCOL);server.initialized=True
    view=protocol.view();c=view['candidates'][0]
    reply=server.handle(dict(jsonrpc='2.0',id=1,method='tools/call',params=dict(name='decision_select',arguments=dict(
        snapshot=view['snapshot'],candidate_id=c['id'],basis={'task_quote':'total distance','criterion':'matching target'},
        comparisons={x['id']:'alternative' for x in view['candidates'][1:]}))))
    assert reply['result']['isError']
    worker=Server(protocol.store,'worker','worker',protocol=PROTOCOL);worker.initialized=True
    result=worker.handle(dict(jsonrpc='2.0',id=2,method='tools/call',params=dict(name='decision_read',
        arguments={'candidate_id':c['id'],'role':'lead'})))
    assert result['result']['isError']
    with protocol.store.connect() as db:
        errors=[json.loads(r[0]) for r in db.execute('SELECT body FROM events') if json.loads(r[0])['method']=='workspace.error']
    assert len(errors)==2


def test_actor_scoped_idempotency_and_kind_query_are_preserved(protocol):
    args={'tool_name':'Bash','tool_input':{},'tool_output':'ok','status':'success','completeness':'complete'}
    a=protocol.store.call('obs.capture',args,actor='a',role='collector',operation_id='same')
    assert a==protocol.store.call('obs.capture',args,actor='a',role='collector',operation_id='same')
    b=protocol.store.call('obs.capture',args,actor='b',role='collector',operation_id='same')
    assert a['id']!=b['id']
    with pytest.raises(StoreError):protocol.store.call('obs.capture',dict(args,tool_output='changed'),actor='a',role='collector',operation_id='same')
    with protocol.store.connect() as db:
        protocol.store.put(db,'unrelated',{'text':'private'},'fixture')
        statements=[];db.set_trace_callback(statements.append)
        assert len(protocol.store.latest(db,'observation'))==2
        assert any("WHERE kind='observation'" in q for q in statements)


def test_sharing_deduplicates_exact_content_but_not_changed_results(protocol):
    context_reply(protocol.store,event(),'full')
    first=emit(protocol,{'answer':2},'first')
    emit(protocol,{'answer':2},'duplicate')
    changed=emit(protocol,{'answer':3},'changed')
    reply=context_reply(protocol.store,event(),'full')
    assert {i['observation']['id'] for i in delivered(reply)}=={first['id'],changed['id']}
    assert context_reply(protocol.store,event(),'full')=={}
    with protocol.store.connect() as db:
        assert len(protocol.store.latest(db,'observation'))==3


def test_candidate_access_survives_unrelated_changes_but_selection_does_not(protocol):
    emit(protocol,measurement(2,TARGET,{'method':'a'},answer_target=True),'a')
    emit(protocol,measurement(3,TARGET,{'method':'b'},answer_target=True),'b')
    for c in protocol.view()['candidates']:protocol.read(c['id'])
    select(protocol)
    emit(protocol,measurement(2,TARGET,{'method':'new'},answer_target=True),'change')
    view=protocol.view();candidates={c['value']:c for c in view['candidates']}
    assert candidates[3]['evidence_access']['complete']
    assert not candidates[2]['evidence_access']['complete']
    assert protocol.check({'answer':2})['reason']=='selection_stale'
    with pytest.raises(StoreError,match='Required decision_read arguments') as error:select(protocol)
    assert candidates[2]['id'] in str(error.value) and candidates[3]['id'] not in str(error.value)
    protocol.read(**candidates[2]['evidence_access']['next_read'])
    select(protocol)


def test_new_candidate_does_not_require_rereading_existing_candidate(protocol):
    emit(protocol,{'answer':2},'first')
    c=protocol.view()['candidates'][0];protocol.read(c['id'])
    emit(protocol,{'answer':3},'second')
    old=next(x for x in protocol.view()['candidates'] if x['id']==c['id'])
    assert old['evidence_access']['complete']
    assert not protocol.view(actor='other')['candidates'][0]['evidence_access']['complete']


def test_partial_read_reports_exact_next_text_page(protocol):
    emit(protocol,{'answer':2,'diagnostic':'x'*20000},'a')
    c=protocol.view()['candidates'][0]
    first=protocol.read(c['id'],limit=100)
    assert first['evidence_access']['next_read']==dict(candidate_id=c['id'],source_cursor=0,start=100)
    assert not first['evidence_access']['complete']


def test_mixed_answer_shapes_warn_without_silent_candidate_rewrite(protocol):
    emit(protocol,{'answer':{'estimate':2,'diagnostic':3}},'object')
    emit(protocol,{'answer':2},'scalar')
    view=protocol.view()
    assert view['representation_warning'] and view['conflict']
    assert len(view['candidates'])==2


def test_wait_guard_requires_explicit_agent_wait_and_observed_shutdown(protocol):
    from harness.evidence_mas.hook import wait_guard
    e=dict(hook_event_name='PreToolUse',session_id='s',tool_name='Bash',
           tool_input={'command':'sleep 60; echo waited','description':'Wait for subagent'})
    assert wait_guard(protocol.store,e) is None
    collect(protocol.store,dict(hook_event_name='SubagentStart',agent_id='w',session_id='s'))
    assert wait_guard(protocol.store,e) is None
    collect(protocol.store,dict(hook_event_name='SubagentStop',agent_id='w',session_id='s'))
    assert wait_guard(protocol.store,e)['hookSpecificOutput']['permissionDecision']=='deny'
    assert wait_guard(protocol.store,dict(e,tool_input={'command':'sleep 60','description':'Wait for disk flush'})) is None
    assert wait_guard(protocol.store,dict(e,tool_input={'command':'sleep 60; python compute.py','description':'Wait for subagent'})) is None
    assert wait_guard(protocol.store,dict(e,agent_id='w')) is None
    collect(protocol.store,dict(hook_event_name='PreToolUse',tool_name='Agent',tool_use_id='pending',session_id='s'))
    assert wait_guard(protocol.store,e) is None


@pytest.mark.parametrize('command,expected', [
    ('sleep 30', True), ('/bin/sleep 0.5;', True),
    ('sleep 60; echo waited', True), ('sleep 40; echo done', True),
    ('sleep 30; echo "$SECRET"', False),
    ('while kill -0 "$pid"; do sleep 1; done', False),
    ('python compute.py; sleep 1', False), ('echo "sleep 30"', False),
    ('sleep $(compute)', False), ('sleep infinity', False)])
def test_wait_advice_does_not_parse_or_rewrite_real_work(command, expected):
    assert pure_delay(dict(hook_event_name='PostToolUse', tool_name='Bash',
                           tool_input={'command': command})) is expected
