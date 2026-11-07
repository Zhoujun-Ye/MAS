"""Offline full-scale admission, crash recovery and memory evidence."""

import json
import multiprocessing
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from common.journal import Journal,exclusive
from harness.runtime_support.admission import admit_balance,fatal_provider_record,BalanceWatch
from harness.runtime_support.resources import memory_sample,memory_summary
from scripts.studies import benchmark_matrix as matrix


def balance(value='100',currency='CNY'):
    return dict(response=dict(is_available=True,balance_infos=[dict(currency=currency,total_balance=value)]))


def test_full_manifest_unequal_pools_and_original_order(tmp_path,monkeypatch,capsys):
    pools={b:[SimpleNamespace(id=f'{b}-{i}',query='private question') for i in range(n)]
           for b,n in [('kramabench',104),('dataclawbench',492)]}
    monkeypatch.setattr(matrix,'task_pools',lambda root,names:pools)
    manifest=dict(kind='benchmark-full-v1',benchmarks={b:[dict(task_id=t.id,task_sha256=matrix.task_fingerprint(b,t))
        for t in tasks] for b,tasks in pools.items()})
    rows=matrix.manifest_selections(tmp_path,manifest,0,None)
    assert len(rows)==596 and [t.id for b,t in rows if b=='kramabench']==[t.id for t in pools['kramabench']]
    manifest['benchmarks']['kramabench'].pop()
    with pytest.raises(ValueError,match='cover every'):matrix.manifest_selections(tmp_path,manifest,0,None)


def test_full_cli_plans_all_104_with_16_slots_without_loading_credentials(tmp_path,monkeypatch,capsys):
    tasks=[SimpleNamespace(id=f'k-{i}',query='private') for i in range(104)]
    monkeypatch.setattr(matrix,'task_pools',lambda *a:{'kramabench':tasks})
    monkeypatch.setattr(matrix.runtime,'credential',lambda *a:pytest.fail('Plan read credentials'))
    manifest=dict(kind='benchmark-full-v1',benchmarks={'kramabench':[
        dict(task_id=t.id,task_sha256=matrix.task_fingerprint('kramabench',t)) for t in tasks]})
    path=tmp_path/'manifest.json';path.write_text(json.dumps(manifest))
    assert 'private' not in path.read_text()
    assert matrix.main(['--root',str(tmp_path),'--output',str(tmp_path/'out'),'--proofs',str(tmp_path),
        '--image','fixture','--benchmarks','kramabench','--conditions','claude-code-subagents','full',
        '--task-manifest',str(path),'--all-tasks','--concurrency','16','--judge-concurrency','4'])==0
    plan=json.loads(capsys.readouterr().out)
    assert plan['attempts']==208 and plan['solver_concurrency']==16 and plan['judge_concurrency']==4
    assert [r['task_id'] for r in plan['selections'][::2]]==[t.id for t in tasks]
    assert not (tmp_path/'out').exists()


@pytest.mark.parametrize('value,currency,estimate,factor,reserve',[
    ('10','CNY','10','1.5','1'),('100','USD','10','1.5','1'),
    ('100','CNY','NaN','1.5','1'),('100','CNY','10','.5','1')])
def test_balance_admission_fails_closed(value,currency,estimate,factor,reserve):
    with pytest.raises(ValueError):admit_balance(balance(value,currency),'CNY',estimate,factor,reserve)


def test_balance_policy_and_polling_have_no_implicit_conversion():
    result=admit_balance(balance(),'CNY','10','1.5','1')
    assert result['required']=='16.0'
    calls=[]
    watch=BalanceWatch(lambda:calls.append(1) or balance(),'CNY','1')
    watch.check();watch.check();assert len(calls)==1
    watch=BalanceWatch(lambda:balance('1'),'CNY','1')
    with pytest.raises(ValueError,match='reserve'):watch.check()


def test_host_http_fatal_is_independent_of_provider_error_text(tmp_path):
    p=tmp_path/'ledger.jsonl'
    row=dict(event='finished',route='/anthropic/v1/messages',upstream_attempted=True,http_status=402)
    p.write_text(json.dumps(row)+'\n{partial')
    assert fatal_provider_record(p)['http_status']==402
    row['upstream_attempted']=False;p.write_text(json.dumps(row))
    assert fatal_provider_record(p) is None
    row['upstream_attempted']=True;row['http_status']=503;p.write_text(json.dumps(row))
    assert fatal_provider_record(p) is None


def test_memory_peak_and_oom_are_not_missing_equals_zero(tmp_path):
    assert memory_sample(tmp_path)['events'] is None
    assert memory_summary([])['oom_observed'] is None
    (tmp_path/'memory.current').write_text('123')
    (tmp_path/'memory.peak').write_text('456')
    (tmp_path/'memory.events').write_text('oom 0\noom_kill 0\nmax 0\n')
    first=memory_sample(tmp_path)
    (tmp_path/'memory.events').write_text('oom 2\noom_kill 1\nmax 3\n')
    result=memory_summary([dict(memory=first),dict(memory=memory_sample(tmp_path))])
    assert result['oom_observed'] and result['cgroup_peak_bytes']==456


def test_journal_claim_is_committed_and_never_implicitly_replayed(tmp_path):
    journal=Journal(tmp_path/'journal.sqlite');key=('b','t','k')
    journal.claim('solver',key,'frozen',{'status':'dispatch_unknown'})
    assert Journal(journal.path).get('solver',key)['state']=='claimed'
    with pytest.raises(Exception):journal.claim('solver',key,'frozen',{})
    with exclusive(tmp_path/'lock'):
        with pytest.raises(ValueError,match='owned'):
            with exclusive(tmp_path/'lock'):pass


def test_continuation_requires_a_journal_even_with_a_sealed_summary(tmp_path):
    summary=dict(interrupted=True,authorization=dict(protocol_settings={},task_manifest_sha256='frozen'),rows=[])
    (tmp_path/'summary.json').write_text(json.dumps(summary))
    with pytest.raises(ValueError,match='durable journal'):
        matrix.retained_attempts(tmp_path,[],{},'frozen')


def setup_matrix(tmp_path,monkeypatch):
    tasks=[('kramabench',SimpleNamespace(id=f'fixture-{i}',query='public')) for i in range(2)]
    monkeypatch.setattr(matrix,'selections',lambda *a:tasks)
    monkeypatch.setattr(matrix,'runtime_preflight',lambda *a:dict(image_id='fixture'))
    monkeypatch.setattr(matrix.runtime,'source_manifest',lambda:{'fixture.py':'same'})
    monkeypatch.setattr(matrix.runtime,'credential',lambda *a:'synthetic-only')
    monkeypatch.setattr(matrix.runtime,'safe_balance',lambda *a:balance())
    def arguments(output,*extra):
        return ['--root',str(tmp_path),'--output',str(output),'--proofs',str(tmp_path),'--image','fixture',
            '--benchmarks','kramabench','--conditions','claude-code-subagents','--concurrency','1',
            '--judge-concurrency','1','--estimated-cost','1','--authorized-attempts','2','--execute',*extra]
    return arguments


class FakeProcess:
    def __init__(self,cmd,**kw):
        if '--execute' in cmd:
            out=Path(cmd[cmd.index('--output')+1]);task=cmd[cmd.index('--task-id')+1]
            folder=out/task/'claude-code-subagents';folder.mkdir(parents=True)
            (folder/'report.json').write_text('{"status":"cli_exited"}')
            (folder/'submission.json').write_text('{"answer":1}')
            (out/'summary.json').write_text('{"rows":[]}')
    def wait(self,**kw):return 0


@pytest.mark.skipif('fork' not in multiprocessing.get_all_start_methods(),reason='Server Linux fork test')
def test_hard_crash_without_summary_never_reruns_unknown_solver(tmp_path,monkeypatch):
    args=setup_matrix(tmp_path,monkeypatch);old=tmp_path/'old';new=tmp_path/'new'
    class Crash:
        def __init__(self,cmd,**kw):
            if '--execute' in cmd:os._exit(137)
        def wait(self,**kw):return 0
    monkeypatch.setattr(matrix.subprocess,'Popen',Crash)
    process=multiprocessing.get_context('fork').Process(target=lambda:matrix.main(args(old)))
    process.start();process.join(15);assert process.exitcode==137
    assert not (old/'summary.json').exists()
    launched=[]
    class Record(FakeProcess):
        def __init__(self,cmd,**kw):
            if '--execute' in cmd:launched.append(cmd[cmd.index('--task-id')+1])
            super().__init__(cmd,**kw)
    monkeypatch.setattr(matrix.subprocess,'Popen',Record)
    monkeypatch.setattr(matrix,'grade_attempt',lambda b,t,k,*a,**kw:dict(benchmark=b,task_id=t.id,backend=k,status='graded',judge_calls=0))
    assert matrix.main(args(new,'--retain-started-from',str(old)))==1
    assert launched==['fixture-1']
    rows=json.loads((new/'summary.json').read_text())['rows']
    assert next(r for r in rows if r['task_id']=='fixture-0')['status']=='dispatch_unknown'


@pytest.mark.skipif('fork' not in multiprocessing.get_all_start_methods(),reason='Server Linux fork test')
def test_crash_during_grading_reuses_complete_and_preserves_unknown(tmp_path,monkeypatch):
    args=setup_matrix(tmp_path,monkeypatch);old=tmp_path/'old';new=tmp_path/'new'
    monkeypatch.setattr(matrix.subprocess,'Popen',FakeProcess)
    def grade(b,t,k,*a,**kw):
        if t.id=='fixture-1':os._exit(139)
        return dict(benchmark=b,task_id=t.id,backend=k,status='graded',judge_calls=1)
    monkeypatch.setattr(matrix,'grade_attempt',grade)
    process=multiprocessing.get_context('fork').Process(target=lambda:matrix.main(args(old,'--authorized-judges','2')))
    process.start();process.join(15);assert process.exitcode==139
    monkeypatch.setattr(matrix,'grade_attempt',lambda *a,**kw:pytest.fail('No grading replay allowed'))
    monkeypatch.setattr(matrix.subprocess,'Popen',lambda *a,**kw:pytest.fail('No solver replay allowed'))
    assert matrix.main(args(new,'--retain-started-from',str(old),'--authorized-judges','2'))==1
    grades=json.loads((new/'summary.json').read_text())['grades']
    assert next(r for r in grades if r['task_id']=='fixture-0')['reused_without_dispatch']
    assert next(r for r in grades if r['task_id']=='fixture-1')['status']=='grading_outcome_unknown'


def test_resume_chain_inherits_started_claims_even_before_copying_rows(tmp_path,monkeypatch):
    setup_matrix(tmp_path,monkeypatch)
    settings={};task=SimpleNamespace(id='fixture-0');old=tmp_path/'old';middle=tmp_path/'middle'
    old.mkdir();middle.mkdir()
    auth=dict(protocol_settings=settings,task_manifest_sha256='manifest',source_manifest={'fixture.py':'same'})
    (old/'authorization.json').write_text(json.dumps(auth))
    j=Journal(old/'journal.sqlite');body=dict(benchmark='kramabench',task_id=task.id,backend='full',
        status='dispatch_unknown',run=str(old/'solvers/kramabench'/task.id/'full'))
    j.claim('solver',('kramabench',task.id,'full'),'frozen',body)
    (middle/'authorization.json').write_text(json.dumps(dict(auth,retained_from=str(old))))
    Journal(middle/'journal.sqlite')
    jobs=[('kramabench',task,'full',tmp_path/'new/solvers'/task.id/'full')]
    rows=matrix.retained_attempts(middle,jobs,settings,'manifest')
    assert rows[('kramabench',task.id,'full')]['status']=='dispatch_unknown'
    monkeypatch.setattr(matrix.runtime,'source_manifest',lambda:{'changed':'source'})
    with pytest.raises(ValueError,match='source changed'):matrix.retained_attempts(middle,jobs,settings,'manifest')


def test_matrix_fatal_host_record_stops_queued_solves_without_log_markers(tmp_path,monkeypatch):
    import time
    args=setup_matrix(tmp_path,monkeypatch);launched=[]
    class Fatal(FakeProcess):
        def __init__(self,cmd,**kw):
            self.paid='--execute' in cmd;self.terminated=False
            super().__init__(cmd,**kw)
            if self.paid:
                launched.append(cmd[cmd.index('--task-id')+1]);out=Path(cmd[cmd.index('--output')+1])
                folder=out/launched[-1]/'claude-code-subagents'
                (folder/'gateway-requests.jsonl').write_text(json.dumps(dict(event='finished',
                    route='/anthropic/v1/messages',upstream_attempted=True,http_status=402)))
        def terminate(self):self.terminated=True
        def wait(self,**kw):
            if self.paid:
                for _ in range(30):
                    if self.terminated:break
                    time.sleep(.1)
            return 0
    monkeypatch.setattr(matrix.subprocess,'Popen',Fatal)
    assert matrix.main(args(tmp_path/'out'))==1
    assert launched==['fixture-0']
    assert json.loads((tmp_path/'out/fatal-provider-error.json').read_text())['http_status']==402


def test_balance_reserve_pauses_before_paid_process_without_killing_work(tmp_path,monkeypatch):
    args=setup_matrix(tmp_path,monkeypatch);calls=[]
    monkeypatch.setattr(matrix.runtime,'safe_balance',lambda *a:calls.append(1) or balance('100' if len(calls)==1 else '0'))
    class NoPaid:
        def __init__(self,cmd,**kw):assert '--execute' not in cmd
        def wait(self,**kw):return 0
    monkeypatch.setattr(matrix.subprocess,'Popen',NoPaid)
    assert matrix.main(args(tmp_path/'out'))==1
    assert (tmp_path/'out/balance-paused.json').exists()
    assert all(r['status']=='not_started' for r in json.loads((tmp_path/'out/summary.json').read_text())['rows'])
