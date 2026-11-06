from concurrent.futures import ThreadPoolExecutor
import json
import subprocess
import sys

import pytest

from harness.evidence_mas.hook import collect
from harness.evidence_mas.store import Store, StoreError


def native_message():
    canonical={'to':'worker-1','summary':'Check data','message':'Check the fixture data'}
    before=dict(canonical,type='message',recipient='worker-1',content='Compatibility message')
    common=dict(session_id='session',tool_use_id='call',tool_name='SendMessage')
    return (dict(common,hook_event_name='PreToolUse',tool_input=before),
            dict(common,hook_event_name='PostToolUse',tool_input=canonical,tool_response={'delivered':True}))


@pytest.mark.parametrize('reverse',[False,True])
def test_native_message_preserves_both_raw_inputs_and_result(tmp_path,reverse):
    store=Store(tmp_path/'store','test');pre,post=native_message()
    events=[post,pre] if reverse else [pre,post]
    for event in events: collect(store,event)
    with store.connect() as db: obs=store.latest(db,'observation')[0]
    assert obs['status']=='success'
    assert obs['input_transform']=='native_send_message_alias_pruning'
    assert store.read_blob(obs['input_ref'])==pre['tool_input']
    assert store.read_blob(obs['terminal_input_ref'])==post['tool_input']
    assert store.read_blob(obs['output_ref'])==post['tool_response']
    assert collect(store,post)['id']==obs['id']
    assert collect(store,pre)['id']==obs['id']
    with store.connect() as db:assert len(store.latest(db,'observation'))==1


def test_parallel_native_message_hooks_reconcile_without_dropping_result(tmp_path):
    store=Store(tmp_path/'store','test');pre,post=native_message()
    with ThreadPoolExecutor(4) as pool:
        list(pool.map(lambda event:collect(store,event),[pre,post,post,pre]))
    with store.connect() as db:obs=store.latest(db,'observation')[0]
    assert obs['status']=='success' and store.read_blob(obs['terminal_input_ref'])==post['tool_input']


@pytest.mark.parametrize('change',['message','to','tool','extra'])
def test_true_conflicts_still_fail_without_mutating_observation(tmp_path,change):
    store=Store(tmp_path/'store','test');pre,post=native_message();initial=collect(store,pre)
    if change in ('message','to'):post['tool_input'][change]='different'
    elif change=='tool':post['tool_name']='Bash'
    else:post['tool_input']['unexpected']='value'
    with pytest.raises(StoreError) as caught:collect(store,post)
    assert caught.value.code=='tool_call_identity_conflict'
    with store.connect() as db:assert store.latest(db,'observation')==[initial]


def test_degraded_diagnostics_are_actionable_without_payload_disclosure(tmp_path):
    root=tmp_path/'store';pre,post=native_message()
    command=[sys.executable,'-m','harness.evidence_mas.hook','--root',str(root),'--run-id','test']
    subprocess.run(command,input=json.dumps(pre),text=True,capture_output=True,check=True)
    post['tool_input']['message']='PRIVATE_PAYLOAD'
    result=subprocess.run(command,input=json.dumps(post),text=True,capture_output=True,check=True)
    assert json.loads(result.stdout)=={}
    receipt=(root/'degraded.jsonl').read_text()
    assert 'PRIVATE_PAYLOAD' not in receipt+result.stderr+result.stdout
    row=json.loads(receipt)
    assert row['error_code']=='tool_call_identity_conflict' and row['tool_name']=='SendMessage'
    assert row['hook_event']=='PostToolUse' and len(row['event_sha256'])==64


@pytest.mark.parametrize('payload',['[]','{"hook_event_name":"PostToolUse","tool_name":"Bash","tool_response":NaN}'])
def test_invalid_event_does_not_break_permission_neutral_reply(tmp_path,payload):
    command=[sys.executable,'-m','harness.evidence_mas.hook','--root',str(tmp_path/'store'),'--run-id','test']
    result=subprocess.run(command,input=payload,text=True,capture_output=True,check=True)
    assert json.loads(result.stdout)=={}
    assert (tmp_path/'store/degraded.jsonl').exists()


def test_terminal_result_without_payload_is_not_silently_overwritten(tmp_path):
    store=Store(tmp_path/'store','test')
    args=dict(tool_name='Bash',tool_input={},session_id='s',tool_call_id='c',status='failed',completeness='missing')
    initial=store.call('obs.capture',args,role='collector')
    with pytest.raises(StoreError):
        store.call('obs.capture',dict(args,status='success'),role='collector')
    with store.connect() as db:assert store.latest(db,'observation')==[initial]
