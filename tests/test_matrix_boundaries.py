"""Offline accounting, orphan-process and terminal-export crash boundaries."""

import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from common.io import fingerprint, write_json
from harness.runtime_support import runtime
from scripts.studies import finalization
from scripts.studies import benchmark_matrix as matrix


def balance(value='100',currency='CNY'):
    return dict(response=dict(is_available=True,balance_infos=[dict(currency=currency,total_balance=value)]))


@pytest.mark.parametrize('invalid',[None,{},[],{'response':None},
    {'response':{'is_available':False}}, {'response':{'is_available':True,'balance_infos':[{}]}},
    balance('NaN'),balance('Infinity'),balance('-1'),balance('10','USD'),
    {'response':{'is_available':True,'balance_infos':[dict(currency='CNY',total_balance='10')]*2}}])
def test_accounting_observation_failure_is_unknown_not_an_exception(invalid):
    assert runtime.observed_balance_deltas(balance(),invalid) is None
    assert runtime.observed_balance_deltas(invalid,balance()) is None


def test_accounting_valid_measurement_including_credit_is_not_hidden():
    assert runtime.observed_balance_deltas(balance('10'),balance('8'))=={'CNY':'2'}
    assert runtime.observed_balance_deltas(balance('8'),balance('10'))=={'CNY':'-2'}


@pytest.mark.parametrize('flag,relative',[('--output','grades/task/backend'),('--run','solvers/task/backend')])
def test_orphan_grader_prevents_continuation(tmp_path,flag,relative):
    child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)',flag,str(tmp_path/relative)])
    try:
        with pytest.raises(ValueError,match='still live'):
            matrix.assert_quiescent(tmp_path)
    finally:
        child.terminate();child.wait(timeout=5)


@pytest.mark.parametrize('state',['absent','stopped','running','daemon-error','inspect-error','malformed'])
def test_container_quiescence_does_not_parse_docker_error_wording(tmp_path,monkeypatch,state):
    write_json(tmp_path/'solvers/task/container-ownership.json',dict(container_name='mas-cli6-fixture'))
    commands=[]
    def run(command,**kwargs):
        commands.append(command)
        if command[1]=='ps':
            assert command[-1]=='name=^/mas\\-cli6\\-fixture$'
            return subprocess.CompletedProcess(command,1 if state=='daemon-error' else 0,
                '' if state=='absent' else 'abc123\n','no such file: docker.sock' if state=='daemon-error' else '')
        return subprocess.CompletedProcess(command,1 if state=='inspect-error' else 0,
            'true\n' if state=='running' else 'unknown\n' if state=='malformed' else 'false\n','')
    monkeypatch.setattr(matrix.subprocess,'run',run)
    if state in {'absent','stopped'}:matrix.assert_quiescent(tmp_path)
    else:
        with pytest.raises(ValueError):matrix.assert_quiescent(tmp_path)
    if state in {'absent','daemon-error'}:assert len(commands)==1


@pytest.mark.parametrize('benchmark',['dataclawbench','hybriddeepresearch','kramabench'])
def test_terminal_export_recovery_is_offline_and_preserves_original(tmp_path,monkeypatch,benchmark):
    from scripts.common import run as external
    from scripts.kramabench import cli_runtime as krama
    task=SimpleNamespace(id='fixture');backend='claude-code-subagents'
    original=tmp_path/'original';folder=original/task.id/backend
    (folder/'workspace').mkdir(parents=True)
    record=dict(instance_id=task.id,task_id=task.id,backend=backend,status='cli_exited',final_answer='')
    write_json(folder/'report.json',record)
    before=(folder/'report.json').read_bytes()
    write_json(original/'plan.json',dict(assets={},inputs_sha256=fingerprint({'lake':'frozen'})))
    (folder/'workspace/submission.json').write_text('{"final_answer":"fixture"}')
    called=[]
    def finish(folder,args,record):
        called.append(True)
        record=dict(record,final_answer='fixture',grade=dict(status='graded',score=1))
        write_json(folder/'report.json',record)
        return record
    monkeypatch.setattr(external,'finalize_attempt',finish)
    monkeypatch.setattr(external,'attempt',lambda *a:pytest.fail('No solver replay'))
    monkeypatch.setattr(krama,'collect_attempt',lambda folder,record,args:finish(folder,args,record))
    monkeypatch.setattr(krama,'run_attempt',lambda *a:pytest.fail('No solver replay'))
    monkeypatch.setattr(krama,'verify_inputs',lambda *a:{'lake':'frozen'})
    assert finalization.needed(benchmark,task,backend,original)
    target=tmp_path/'recovered'
    recovered=finalization.recover(benchmark,task,backend,original,target,root=tmp_path,image='fixture')
    assert recovered['grade']['score']==1 and called==[True]
    assert not finalization.needed(benchmark,task,backend,target)
    assert (folder/'report.json').read_bytes()==before
    assert not (original/'predictions.jsonl').exists()
    assert json.loads((target/'offline-finalization.json').read_text())['model_calls']==0
    with pytest.raises(FileExistsError):
        finalization.recover(benchmark,task,backend,original,target,root=tmp_path,image='fixture')


def test_stale_placeholder_prediction_is_detected(tmp_path):
    task=SimpleNamespace(id='fixture');backend='claude-code-subagents'
    folder=tmp_path/task.id/backend;folder.mkdir(parents=True)
    write_json(folder/'report.json',dict(instance_id=task.id,status='cli_exited',final_answer='final'))
    (tmp_path/'predictions.jsonl').write_text(json.dumps(dict(instance_id=task.id,status='not_started',final_answer=''))+'\n')
    assert finalization.needed('dataclawbench',task,backend,tmp_path)


def test_recovery_rejects_changed_inputs_before_copy(tmp_path):
    source=tmp_path/'source';source.mkdir();asset=tmp_path/'asset';asset.write_text('changed')
    write_json(source/'plan.json',dict(assets={str(asset):'frozen-other-digest'}))
    with pytest.raises(ValueError,match='inputs changed'):
        finalization.recover('dataclawbench',SimpleNamespace(id='fixture'),'claude-code-subagents',
            source,tmp_path/'new',root=tmp_path,image='fixture')
    assert not (tmp_path/'new').exists()


def test_nonempty_malformed_final_balance_keeps_matrix_summary(tmp_path,monkeypatch):
    from test_fullscale_infra import setup_matrix,FakeProcess
    args=setup_matrix(tmp_path,monkeypatch)
    monkeypatch.setattr(matrix.subprocess,'Popen',FakeProcess)
    monkeypatch.setattr(matrix.runtime,'safe_balance',lambda key,root,name:{} if name=='balance-after' else balance())
    monkeypatch.setattr(matrix,'grade_attempt',lambda b,t,k,*a,**kw:dict(benchmark=b,task_id=t.id,
        backend=k,status='graded',judge_calls=0))
    assert matrix.main(args(tmp_path/'out'))==0
    assert json.loads((tmp_path/'out/summary.json').read_text())['account_delta'] is None


@pytest.mark.skipif('fork' not in multiprocessing.get_all_start_methods(),reason='Linux fault injection')
def test_hard_crash_after_solver_report_finalizes_without_resolving_task(tmp_path,monkeypatch):
    from test_fullscale_infra import setup_matrix,FakeProcess
    args=setup_matrix(tmp_path,monkeypatch);old=tmp_path/'old'
    class Crash(FakeProcess):
        def __init__(self,cmd,**kw):
            super().__init__(cmd,**kw)
            if '--execute' in cmd:
                out=Path(cmd[cmd.index('--output')+1]);(out/'summary.json').unlink()
                os._exit(137)
    monkeypatch.setattr(matrix.subprocess,'Popen',Crash)
    child=multiprocessing.get_context('fork').Process(target=lambda:matrix.main(args(old)))
    child.start();child.join(15);assert child.exitcode==137
    launched=[];repaired=[]
    class Record(FakeProcess):
        def __init__(self,cmd,**kw):
            if '--execute' in cmd:launched.append(cmd[cmd.index('--task-id')+1])
            super().__init__(cmd,**kw)
    monkeypatch.setattr(matrix.subprocess,'Popen',Record)
    def repair(b,t,k,run,target,**kw):
        repaired.append(t.id)
        folder=target/t.id/k;folder.mkdir(parents=True)
        record=dict(task_id=t.id,backend=k,status='cli_exited')
        write_json(folder/'report.json',record)
        write_json(target/'summary.json',dict(rows=[dict(record,grade=dict(status='graded',score=1))]))
        return record
    monkeypatch.setattr(matrix.finalization,'recover',repair)
    monkeypatch.setattr(matrix,'grade_attempt',lambda b,t,k,*a,**kw:dict(benchmark=b,task_id=t.id,
        backend=k,status='graded',judge_calls=0))
    assert matrix.main(args(tmp_path/'new','--retain-started-from',str(old)))==0
    assert launched==['fixture-1'] and repaired==['fixture-0']
    assert not (old/'solvers/kramabench/fixture-0/claude-code-subagents/summary.json').exists()
