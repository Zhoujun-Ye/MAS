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
        '--image','fixture','--benchmarks','kramabench','--conditions','claude-code-subagents','claude-code-single-agent',
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


def test_balance_transients_are_bounded_and_malformed_responses_do_not_crash_monitor():
    watch=BalanceWatch(lambda: {'response': {'is_available':True,'balance_infos':[{}]}},
                       'CNY','1',interval=0,initial=balance())
    watch.check();watch.check()
    with pytest.raises(ValueError,match='repeatedly'):watch.check()
    watch.fetch=lambda:balance('0')
    with pytest.raises(ValueError,match='reserve'):watch.check()


@pytest.mark.parametrize('record,expected',[
    (None,'not_started'), ('','not_started'),
    ('{"event":"started","upstream_attempted":false}','not_started'),
    ('{"event":"dispatched","upstream_attempted":true}','dispatch_unknown'),
    ('{partial','dispatch_unknown')])
def test_dispatch_classification_uses_write_ahead_evidence(tmp_path,record,expected):
    if record is not None:(tmp_path/'gateway-requests.jsonl').write_text(record)
    assert matrix.solver_dispatch_status(tmp_path)==expected


def test_free_grading_ignores_balance_pause_and_overlaps_solving(tmp_path,monkeypatch):
    import threading
    args=setup_matrix(tmp_path,monkeypatch)
    first_graded=threading.Event()
    second_started=threading.Event()
    class Overlap(FakeProcess):
        def __init__(self,cmd,**kw):
            self.second='--execute' in cmd and cmd[cmd.index('--task-id')+1]=='fixture-1'
            self.first='--execute' in cmd and not self.second
            super().__init__(cmd,**kw)
            if self.second:second_started.set()
        def wait(self,**kw):
            if self.first:assert second_started.wait(5)
            if self.second:
                import time
                assert first_graded.wait(5),'Grading waited for all solvers'
                deadline=time.monotonic()+3
                while not (tmp_path/'out/grading-progress.json').exists() and time.monotonic()<deadline:time.sleep(.01)
                assert (tmp_path/'out/grading-progress.json').exists(),'Progress withheld until every solver finishes'
            return 0
    monkeypatch.setattr(matrix.subprocess,'Popen',Overlap)
    class Watch:
        def __init__(self,*a,**kw):pass
        def check(self):
            if first_graded.is_set():raise ValueError('reserve')
    monkeypatch.setattr(matrix,'BalanceWatch',Watch)
    def grade(b,t,k,*a,**kw):
        first_graded.set()
        return dict(benchmark=b,task_id=t.id,backend=k,status='graded',judge_calls=0)
    monkeypatch.setattr(matrix,'grade_attempt',grade)
    # Both solves launch before the first grade; the second completes only after it.
    matrix.main(args(tmp_path/'out','--concurrency','2'))
    summary=json.loads((tmp_path/'out/summary.json').read_text())
    assert len(summary['grades'])==2
    assert all(g['status']=='graded' for g in summary['grades'])


def test_child_timeout_pauses_dispatch_without_global_termination(tmp_path,monkeypatch):
    import subprocess
    args=setup_matrix(tmp_path,monkeypatch)
    terminated=[]
    class Hung(FakeProcess):
        def __init__(self,cmd,**kw):
            self.hung='--execute' in cmd
            super().__init__(cmd,**kw)
        def wait(self,**kw):
            if self.hung and not terminated:raise subprocess.TimeoutExpired('fixture',1)
            return 0
        def terminate(self):terminated.append('only hung child')
    monkeypatch.setattr(matrix.subprocess,'Popen',Hung)
    monkeypatch.setattr(matrix,'default_timeout',lambda b:-601)
    monkeypatch.setattr(matrix,'grade_attempt',lambda b,t,k,*a,**kw:dict(benchmark=b,task_id=t.id,backend=k,status='graded',judge_calls=0))
    assert matrix.main(args(tmp_path/'out'))==1
    assert terminated==['only hung child']
    assert (tmp_path/'out/balance-paused.json').exists()
    assert not (tmp_path/'out/fatal-provider-error.json').exists()


def test_monitor_exception_preserves_inflight_child(tmp_path,monkeypatch):
    import time
    args=setup_matrix(tmp_path,monkeypatch)
    terminated=[]
    class Running(FakeProcess):
        def __init__(self,cmd,**kw):
            self.paid='--execute' in cmd
            super().__init__(cmd,**kw)
            if self.paid:
                out=Path(cmd[cmd.index('--output')+1]);task=cmd[cmd.index('--task-id')+1]
                (out/task/'claude-code-subagents/gateway-requests.jsonl').write_text('[]')
        def wait(self,**kw):
            if self.paid:time.sleep(1.2)
            return 0
        def terminate(self):terminated.append(True)
    monkeypatch.setattr(matrix.subprocess,'Popen',Running)
    monkeypatch.setattr(matrix,'grade_attempt',lambda b,t,k,*a,**kw:dict(benchmark=b,task_id=t.id,backend=k,status='graded',judge_calls=0))
    assert matrix.main(args(tmp_path/'out'))==1
    assert not terminated
    assert (tmp_path/'out/monitor-error.json').exists()
    assert (tmp_path/'out/balance-paused.json').exists()


def test_deterministic_grading_claim_is_safe_to_resume(tmp_path,monkeypatch):
    args=setup_matrix(tmp_path,monkeypatch)
    monkeypatch.setattr(matrix.subprocess,'Popen',FakeProcess)
    def skipped(b,t,k,*a,**kw):
        return dict(benchmark=b,task_id=t.id,backend=k,status='not_started',judge_calls=0)
    monkeypatch.setattr(matrix,'grade_attempt',skipped)
    old=tmp_path/'old'
    assert matrix.main(args(old))==1
    summary=json.loads((old/'summary.json').read_text());summary['interrupted']=True
    (old/'summary.json').write_text(json.dumps(summary))
    called=[]
    def grade(b,t,k,*a,**kw):
        called.append(t.id)
        return dict(benchmark=b,task_id=t.id,backend=k,status='graded',judge_calls=0)
    monkeypatch.setattr(matrix,'grade_attempt',grade)
    monkeypatch.setattr(matrix.subprocess,'Popen',lambda *a,**kw:pytest.fail('Solver replay'))
    assert matrix.main(args(tmp_path/'new','--retain-started-from',str(old)))==0
    assert sorted(called)==['fixture-0','fixture-1']


def test_explicit_judge_recovery_of_sealed_batch_never_replays_solves_or_judges_twice(tmp_path,monkeypatch):
    args=setup_matrix(tmp_path,monkeypatch)
    monkeypatch.setattr(matrix.subprocess,'Popen',FakeProcess)
    monkeypatch.setattr(matrix,'needs_judge',lambda *a:True)
    calls=[]
    def failed(b,t,k,*a,**kw):
        calls.append(t.id)
        artifact=kw['grades_root']/b/t.id/k
        artifact.mkdir(parents=True)
        (artifact/'result.json').write_text(json.dumps(dict(status='judge_error',http_status=503)))
        return dict(benchmark=b,task_id=t.id,backend=k,status='judge_error',judge_calls=1)
    monkeypatch.setattr(matrix,'grade_attempt',failed)
    old=tmp_path/'old';new=tmp_path/'new'
    assert matrix.main(args(old,'--authorized-judges','2'))==1
    monkeypatch.setattr(matrix.subprocess,'Popen',lambda *a,**kw:pytest.fail('Solver replay'))
    assert matrix.main(args(new,'--retain-started-from',str(old),'--authorized-attempts','0',
                           '--authorized-judges','2','--recover-judge-5xx'))==1
    assert len(calls)==4
    assert matrix.main(args(tmp_path/'third','--retain-started-from',str(new),
                           '--authorized-attempts','0','--authorized-judges','0','--recover-judge-5xx'))==1
    assert len(calls)==4


def test_judge_recovery_plan_lists_exact_subset_and_bounds_authorization(tmp_path,monkeypatch,capsys):
    args=setup_matrix(tmp_path,monkeypatch)
    monkeypatch.setattr(matrix.subprocess,'Popen',FakeProcess)
    monkeypatch.setattr(matrix,'needs_judge',lambda *a:True)
    calls=[]
    def failed(b,t,k,*a,**kw):
        calls.append(t.id)
        artifact=kw['grades_root']/b/t.id/k;artifact.mkdir(parents=True)
        code=503 if t.id=='fixture-0' else 429
        (artifact/'result.json').write_text(json.dumps(dict(status='judge_error',http_status=code)))
        return dict(benchmark=b,task_id=t.id,backend=k,status='judge_error',judge_calls=1)
    monkeypatch.setattr(matrix,'grade_attempt',failed)
    old=tmp_path/'old'
    assert matrix.main(args(old,'--authorized-judges','2'))==1
    capsys.readouterr()
    monkeypatch.setattr(matrix.subprocess,'Popen',lambda *a,**kw:pytest.fail('Solver replay'))
    monkeypatch.setattr(matrix.runtime,'credential',lambda *a:pytest.fail('Plan read key'))
    plan_args=args(tmp_path/'new','--retain-started-from',str(old),'--recover-judge-5xx')
    plan_args.remove('--execute')
    assert matrix.main(plan_args)==0
    plan=json.loads(capsys.readouterr().out)
    assert plan['new_solver_attempts']==0 and plan['maximum_judge_calls']==1
    assert [r['task_id'] for r in plan['judge_recovery']]==['fixture-0']
    assert not (tmp_path/'new').exists()
    with pytest.raises(ValueError,match='judge count'):
        matrix.main(args(tmp_path/'new','--retain-started-from',str(old),'--recover-judge-5xx',
                         '--authorized-attempts','0','--authorized-judges','2'))
    monkeypatch.setattr(matrix.runtime,'credential',lambda *a:'synthetic')
    assert matrix.main(args(tmp_path/'new','--retain-started-from',str(old),'--recover-judge-5xx',
                            '--authorized-attempts','0','--authorized-judges','1'))==1
    assert calls==['fixture-0','fixture-1','fixture-0']


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


@pytest.mark.parametrize('status',[None,'launcher_error','interrupted','cli_error'])
def test_report_before_dispatch_remains_resumable_without_replaying_other_solver(tmp_path,monkeypatch,status):
    args=setup_matrix(tmp_path,monkeypatch)
    class BeforeDispatch(FakeProcess):
        def __init__(self,cmd,**kw):
            super().__init__(cmd,**kw)
            if '--execute' in cmd and cmd[cmd.index('--task-id')+1]=='fixture-0':
                folder=Path(cmd[cmd.index('--output')+1])/'fixture-0/claude-code-subagents'
                if status is None:(folder/'report.json').unlink()
                else:(folder/'report.json').write_text(json.dumps(dict(status=status)))
                (folder/'gateway-requests.jsonl').write_text('{"event":"finished","upstream_attempted":false}')
    monkeypatch.setattr(matrix.subprocess,'Popen',BeforeDispatch)
    monkeypatch.setattr(matrix,'grade_attempt',lambda b,t,k,*a,**kw:dict(benchmark=b,task_id=t.id,backend=k,status='graded',judge_calls=0))
    old=tmp_path/'old'
    assert matrix.main(args(old))==1
    summary=json.loads((old/'summary.json').read_text())
    assert summary['interrupted']
    assert next(r for r in summary['rows'] if r['task_id']=='fixture-0')['status']=='not_started'
    launched=[]
    class Recovered(FakeProcess):
        def __init__(self,cmd,**kw):
            if '--execute' in cmd:launched.append(cmd[cmd.index('--task-id')+1])
            super().__init__(cmd,**kw)
    monkeypatch.setattr(matrix.subprocess,'Popen',Recovered)
    assert matrix.main(args(tmp_path/'new','--retain-started-from',str(old)))==0
    assert launched==['fixture-0']


@pytest.mark.parametrize('status',['launcher_error','interrupted','cli_error'])
@pytest.mark.parametrize('state',['claimed','complete'])
def test_resume_reconciles_failed_report_with_host_dispatch_evidence(tmp_path,monkeypatch,status,state):
    setup_matrix(tmp_path,monkeypatch)
    root=tmp_path/'old';root.mkdir()
    (root/'authorization.json').write_text(json.dumps(dict(protocol_settings={},task_manifest_sha256=None,
        source_manifest={'fixture.py':'same'})))
    job=('kramabench',SimpleNamespace(id='fixture-0'),'claude-code-subagents',tmp_path/'new')
    run=root/'solvers/kramabench/fixture-0/claude-code-subagents'
    folder=run/'fixture-0/claude-code-subagents';folder.mkdir(parents=True)
    (folder/'report.json').write_text(json.dumps(dict(status=status)))
    journal=Journal(root/'journal.sqlite');identity=('kramabench','fixture-0','claude-code-subagents')
    body=dict(benchmark='kramabench',task_id='fixture-0',backend='claude-code-subagents',run=str(run),status=status)
    journal.claim('solver',identity,'frozen',body)
    if state=='complete':journal.finish('solver',identity,'frozen',body)
    assert matrix.retained_attempts(root,[job],{},None)=={}
    (folder/'gateway-requests.jsonl').write_text('{"event":"dispatched","upstream_attempted":true}')
    assert matrix.retained_attempts(root,[job],{},None)[identity]['status']==status


@pytest.mark.parametrize('before_ok,after_ok',[(False,True),(True,False),(False,False)])
def test_matrix_managed_krama_balance_gap_does_not_lose_evaluation(tmp_path,monkeypatch,before_ok,after_ok):
    from scripts.kramabench import run
    snapshots=iter([balance() if before_ok else None,balance() if after_ok else None])
    monkeypatch.setattr(run,'safe_balance',lambda *a:next(snapshots))
    monkeypatch.setattr(run.shared,'credential',lambda *a:'synthetic')
    monkeypatch.setattr(run,'monitor',lambda output,stop,active,lock,done:done.wait())
    monkeypatch.setattr(run.signal,'signal',lambda *a:None)
    monkeypatch.setattr(run,'admission',lambda *a:dict(passed=True))
    report=dict(task_id='fixture',backend='claude-code-subagents',status='cli_exited')
    monkeypatch.setattr(run.runtime,'run_attempt',lambda *a:report)
    collected=[]
    def collect(*a):
        collected.append(True)
        return dict(report,grade=dict(status='graded',score=1))
    monkeypatch.setattr(run.runtime,'collect_attempt',collect)
    args=SimpleNamespace(output=tmp_path,credentials=tmp_path/'unused',matrix_balance_managed=True,
                         backends=['claude-code-subagents'],concurrency=1,judge_limit=0)
    run.execute(args,[SimpleNamespace(id='fixture')],dict(admission_task='fixture'))
    assert collected
    assert (tmp_path/'solver-results.json').exists()
    assert json.loads((tmp_path/'summary.json').read_text())['rows'][0]['grade']['score']==1
    assert json.loads((tmp_path/'solver-billing.json').read_text())['balance_delta_by_currency'] is None


@pytest.mark.parametrize('paid',[False,True])
def test_grader_exception_does_not_kill_solving_and_preserves_paid_uncertainty(tmp_path,monkeypatch,paid):
    args=setup_matrix(tmp_path,monkeypatch)
    monkeypatch.setattr(matrix.subprocess,'Popen',FakeProcess)
    monkeypatch.setattr(matrix,'needs_judge',lambda *a:paid)
    calls=[]
    def broken(b,t,k,*a,**kw):
        calls.append(t.id)
        raise RuntimeError('synthetic private error body')
    monkeypatch.setattr(matrix,'grade_attempt',broken)
    old=tmp_path/'old'
    assert matrix.main(args(old,'--authorized-judges','2'))==1
    summary=json.loads((old/'summary.json').read_text())
    assert all(r['status']=='cli_exited' for r in summary['rows'])
    assert len(calls)==2
    assert 'synthetic private error body' not in (old/'summary.json').read_text()
    def fixed(b,t,k,*a,**kw):
        calls.append(t.id)
        return dict(benchmark=b,task_id=t.id,backend=k,status='graded',judge_calls=0)
    monkeypatch.setattr(matrix,'grade_attempt',fixed)
    monkeypatch.setattr(matrix.subprocess,'Popen',lambda *a,**kw:pytest.fail('Solver replay'))
    code=matrix.main(args(tmp_path/'new','--retain-started-from',str(old),'--authorized-judges','2'))
    assert code==(1 if paid else 0)
    assert len(calls)==(2 if paid else 4)


def test_operator_interrupt_stops_even_free_grading(tmp_path,monkeypatch):
    import signal
    args=setup_matrix(tmp_path,monkeypatch);handlers={}
    monkeypatch.setattr(matrix.signal,'signal',lambda number,handler:handlers.setdefault(number,handler))
    class Interrupted(FakeProcess):
        def __init__(self,cmd,**kw):
            self.paid='--execute' in cmd
            super().__init__(cmd,**kw)
        def wait(self,**kw):
            if self.paid:handlers[signal.SIGINT](signal.SIGINT,None)
            return 0
        def terminate(self):pass
    monkeypatch.setattr(matrix.subprocess,'Popen',Interrupted)
    monkeypatch.setattr(matrix,'grade_attempt',lambda *a,**kw:pytest.fail('Operator stopped grading'))
    assert matrix.main(args(tmp_path/'out'))==1
    summary=json.loads((tmp_path/'out/summary.json').read_text())
    assert summary['interrupted'] and all(g['status']=='not_started' for g in summary['grades'])


@pytest.mark.skipif('fork' not in multiprocessing.get_all_start_methods(),reason='Server Linux fork test')
def test_hard_crash_before_dispatch_can_resume_solver(tmp_path,monkeypatch):
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
    assert matrix.main(args(new,'--retain-started-from',str(old)))==0
    assert launched==['fixture-0','fixture-1']
    rows=json.loads((new/'summary.json').read_text())['rows']
    assert next(r for r in rows if r['task_id']=='fixture-0')['status']=='cli_exited'


@pytest.mark.skipif('fork' not in multiprocessing.get_all_start_methods(),reason='Server Linux fork test')
def test_crash_during_grading_reuses_complete_and_preserves_unknown(tmp_path,monkeypatch):
    args=setup_matrix(tmp_path,monkeypatch);old=tmp_path/'old';new=tmp_path/'new'
    monkeypatch.setattr(matrix.subprocess,'Popen',FakeProcess)
    monkeypatch.setattr(matrix,'needs_judge',lambda *a:True)
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
    j=Journal(old/'journal.sqlite');body=dict(benchmark='kramabench',task_id=task.id,backend='claude-code-subagents',
        status='dispatch_unknown',run=str(old/'solvers/kramabench'/task.id/'claude-code-subagents'))
    j.claim('solver',('kramabench',task.id,'claude-code-subagents'),'frozen',body)
    folder=Path(body['run'])/task.id/'claude-code-subagents'
    folder.mkdir(parents=True)
    (folder/'gateway-requests.jsonl').write_text(json.dumps(dict(event='dispatched',upstream_attempted=True)))
    (middle/'authorization.json').write_text(json.dumps(dict(auth,retained_from=str(old))))
    Journal(middle/'journal.sqlite')
    jobs=[('kramabench',task,'claude-code-subagents',tmp_path/'new/solvers'/task.id/'claude-code-subagents')]
    rows=matrix.retained_attempts(middle,jobs,settings,'manifest')
    assert rows[('kramabench',task.id,'claude-code-subagents')]['status']=='dispatch_unknown'
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
