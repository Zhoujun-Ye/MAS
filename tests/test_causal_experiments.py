"""Study permissions, independent donors and one-shot thirty-task scheduling; no paid network."""

from collections import Counter
import io
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace

import pytest

from common.io import fingerprint, read_json, write_json
from scripts.studies.causal_experiments import hooks, runtime, run, report
from scripts.studies.causal_experiments import trial


def test_null_worker_drops_question_description_resume_and_tools(tmp_path):
    payload=dict(hook_event_name='PreToolUse',tool_name='Agent',tool_input=dict(prompt='secret task',
        description='secret task',resume='old-session',subagent_type='Explore',run_in_background=True))
    decision=hooks.intervention(payload,'null_worker',tmp_path)
    updated=decision['hookSpecificOutput']['updatedInput']
    assert 'secret task' not in json.dumps(updated) and 'resume' not in updated
    assert updated['prompt']==hooks.NULL_REQUEST and updated['run_in_background'] is True
    assert payload['causal_intervention']['original_input']['prompt']=='secret task'
    deny=hooks.intervention(dict(hook_event_name='PreToolUse',tool_name='Read',agent_id='worker'),'null_worker',tmp_path)
    assert deny['hookSpecificOutput']['permissionDecision']=='deny'
    message=dict(hook_event_name='PreToolUse',tool_name='SendMessage',tool_input=dict(to='worker',summary='secret task',message='secret task'))
    updated=hooks.intervention(message,'null_worker',tmp_path)['hookSpecificOutput']['updatedInput']
    assert updated['to']=='worker' and 'secret task' not in json.dumps(updated)


def test_free_probe_module_and_null_sentinel_share_one_definition():
    from scripts.studies.causal_experiments import free_probe
    assert free_probe.NULL_REPORT == hooks.NULL_REPORT


@pytest.mark.parametrize('text',['','## Task\ncompute\n## Qualifiers\n\n## Sources\ndata', 'some prose without headings'])
def test_brief_gate_rejects_missing_or_empty_sections(tmp_path,text):
    (tmp_path/'brief.md').write_text(text)
    decision=hooks.intervention(dict(hook_event_name='PreToolUse',tool_name='Bash'),'self_brief',tmp_path)
    assert decision['hookSpecificOutput']['permissionDecision']=='deny'
    (tmp_path/'brief.md').write_text('## Task\ncompute\n## Qualifiers\ndates\n## Sources\ndata')
    assert hooks.intervention(dict(hook_event_name='PreToolUse',tool_name='Bash'),'self_brief',tmp_path)=={}


def test_brief_symlink_never_unlocks_gate(tmp_path):
    real=tmp_path/'real';real.write_text('## Task\nx\n## Qualifiers\ny\n## Sources\nz')
    (tmp_path/'brief.md').symlink_to(real)
    assert not hooks.brief_valid(tmp_path/'brief.md')


def test_study_hook_missing_config_fails_closed_and_preserves_recording(tmp_path,monkeypatch,capsys):
    monkeypatch.setattr(hooks.sys,'argv',['hooks.py','--output',str(tmp_path/'events.jsonl'),'--single-agent'])
    monkeypatch.setattr(hooks.sys,'stdin',io.StringIO(json.dumps(dict(hook_event_name='PreToolUse',tool_name='Bash'))))
    seen=[]
    def baseline(command,**kw):
        seen.append(json.loads(kw['input']));return SimpleNamespace(stdout='{}')
    monkeypatch.setattr(hooks.subprocess,'run',baseline)
    hooks.main()
    assert json.loads(capsys.readouterr().out)['continue'] is False
    assert seen[0]['causal_intervention']['action']=='policy_error'


@pytest.mark.parametrize('badpath',['/workspace/submission.json','/data/../reference.json','relative.csv','/data/missing.csv'])
def test_recon_packet_rejects_noninput_or_missing_sources(tmp_path,badpath):
    (tmp_path/'data').mkdir();work=tmp_path/'donor/workspace';work.mkdir(parents=True)
    write_json(work/'recon.json',dict(task_qualifiers=[],uncertainties=[],candidate_sources=[
        dict(path=badpath,columns=[],units='',relevance='')]))
    with pytest.raises(ValueError):runtime.recon_packet(tmp_path/'donor',tmp_path)


def test_recon_packet_is_not_repaired_or_normalized(tmp_path):
    (tmp_path/'data').mkdir();(tmp_path/'data/input.csv').write_text('a,b\n1,2')
    work=tmp_path/'donor/workspace';work.mkdir(parents=True)
    data=dict(task_qualifiers=['qualifier'],candidate_sources=[dict(path='/data/input.csv',columns=['a','b'],units='unknown',relevance='candidate')],uncertainties=['may be wrong'])
    write_json(work/'recon.json',data)
    assert runtime.recon_packet(tmp_path/'donor',tmp_path)==data
    data['answer']=1;write_json(work/'recon.json',data)
    with pytest.raises(ValueError):runtime.recon_packet(tmp_path/'donor',tmp_path)


def test_default_plan_does_not_read_proofs_credentials_or_launch(tmp_path,monkeypatch,capsys):
    monkeypatch.setattr(run.subprocess,'check_output',lambda *a,**kw:pytest.fail('Plan touched runtime'))
    assert run.main(['--output',str(tmp_path/'run'),'--proof',str(tmp_path/'absent')])==0
    d=json.loads(capsys.readouterr().out)
    assert (d['solvers'],d['independent_recons'],d['maximum_judges'])==(540,90,'actual eligible tasks x six arms x three rounds')
    assert d['review_required'] and not (tmp_path/'run').exists()


def test_paid_execution_is_blocked_before_credentials_without_review(tmp_path,monkeypatch):
    write_json(tmp_path/'plan.json',{})
    monkeypatch.setattr(run.shared,'credential',lambda *a:pytest.fail('Unreviewed execution read credentials'))
    args=SimpleNamespace(output=tmp_path,review_confirmed=False,reviewed_plan_sha256=None,
        authorized_solvers=540,authorized_recons=90,authorized_judges=36)
    with pytest.raises(ValueError,match='Review'):run.execute(args)
    assert not (tmp_path/'execution.json').exists()


def preparation_fixture(tmp_path,monkeypatch):
    binary=tmp_path/'binary';binary.write_bytes(b'synthetic CLI')
    monkeypatch.setattr(run.shared,'CLAUDE',binary)
    monkeypatch.setattr(run.shared,'source_manifest',lambda:{'code':'hash'})
    monkeypatch.setattr(run.os,'cpu_count',lambda:192)
    monkeypatch.setattr(run.subprocess,'check_output',lambda *a,**kw:b'[{"Id":"image-id"}]')
    tasks=[SimpleNamespace(id=f't{i}') for i in range(30)]
    monkeypatch.setattr(run,'selected_tasks',lambda *a:(tasks,{'tasks':[t.id for t in tasks]}))
    monkeypatch.setattr(run,'grade_answer',lambda upstream,t,sub:dict(answer_type='string_approximate' if t in {'t0','t1'} else 'numeric_exact'))
    monkeypatch.setattr(run.krama,'verify_inputs',lambda *a:{'inputs':'hash'})
    proof=tmp_path/'proof.json'
    write_json(proof,dict(passed=True,paid_calls=0,roles={r:dict(passed=True) for r in runtime.ROLES},
        source_manifest={'code':'hash'},runtime_binding=dict(image_id='image-id',binary_sha256=run.sha(binary))))
    args=SimpleNamespace(root=tmp_path,proof=proof,output=tmp_path/'prepared',image='image',
        review_confirmed=True,authorized_solvers=540,authorized_recons=90,authorized_judges=36,estimated_cost='100')
    return args,run.prepare(args)


def test_prepare_round_trip_and_review_binding_before_dispatch(tmp_path,monkeypatch):
    args,plan=preparation_fixture(tmp_path,monkeypatch)
    args.reviewed_plan_sha256=fingerprint(plan)
    assert read_json(args.output/'plan.json')==plan
    assert run.validate_execution(args)==plan
    assert [len(v) for v in plan['schedule'].values()]==[180,180,180]
    assert 'recon_transplant' not in {a for t,a in plan['schedule']['0']}
    assert plan['maximum_judge_calls']==36
    plan['solver_concurrency']=17;write_json(args.output/'plan.json',plan)
    args.reviewed_plan_sha256=fingerprint(plan)
    with pytest.raises(ValueError,match='changed'):run.validate_execution(args)


@pytest.mark.parametrize('change',['source','proof','tasks','review','scope'])
def test_stale_or_unreviewed_preparation_cannot_launch(tmp_path,monkeypatch,change):
    args,plan=preparation_fixture(tmp_path,monkeypatch)
    args.reviewed_plan_sha256=fingerprint(plan)
    if change=='source':monkeypatch.setattr(run.shared,'source_manifest',lambda:{'other':'hash'})
    elif change=='proof':write_json(args.proof,{})
    elif change=='tasks':write_json(args.output/'task-manifest.json',{})
    elif change=='review':args.review_confirmed=False
    else:args.authorized_recons=61
    monkeypatch.setattr(run.shared,'credential',lambda *a:pytest.fail('Invalid plan reached credentials'))
    with pytest.raises(ValueError):run.execute(args)
    assert not (args.output/'execution.json').exists()


def test_trial_without_parent_claim_cannot_read_credentials(tmp_path,monkeypatch):
    plan=dict(source_manifest={'code':'hash'})
    write_json(tmp_path/'plan.json',plan)
    monkeypatch.setattr(trial.shared,'source_manifest',lambda:{'code':'hash'})
    monkeypatch.setattr(trial.shared,'credential',lambda *a:pytest.fail('Unclaimed session read a key'))
    with pytest.raises(ValueError,match='dispatch marker'):
        trial.main(['--plan',str(tmp_path/'plan.json'),'--seed','0','--task','t0','--arm','single',
                    '--credentials',str(tmp_path/'secret'),'--execute'])


def test_changed_donor_packet_is_rejected_before_single_dispatch(tmp_path,monkeypatch):
    from common.journal import Journal
    plan=dict(source_manifest={'code':'hash'},upstream=str(tmp_path),task_ids=['t0'])
    write_json(tmp_path/'plan.json',plan)
    write_json(tmp_path/'execution.json',dict(plan_sha256=fingerprint(plan),review_confirmed=True))
    Journal(tmp_path/'phases.sqlite').claim('session',(0,'t0','recon_transplant'),fingerprint(plan),{})
    donor=tmp_path/'round-0/t0/recon'
    write_json(donor/'packet.json',dict(task_id='t0',packet='changed'))
    write_json(donor/'result.json',dict(recon_receipt=dict(task_id='t0',packet='original')))
    monkeypatch.setattr(trial.shared,'source_manifest',lambda:{'code':'hash'})
    monkeypatch.setattr(trial,'load_tasks',lambda *a:([SimpleNamespace(id='t0')],{}))
    monkeypatch.setattr(trial.shared,'credential',lambda *a:pytest.fail('Changed donor reached credentials'))
    with pytest.raises(ValueError,match='donor packet changed'):
        trial.main(['--plan',str(tmp_path/'plan.json'),'--seed','0','--task','t0','--arm','recon_transplant',
                    '--credentials',str(tmp_path/'secret'),'--execute'])


def execution_fixture(tmp_path,monkeypatch,*,judges=False,fail=False,interrupt=False,deviation=False,infra=False,e4=False):
    root=tmp_path/'run';root.mkdir()
    ids=[f't{i}' for i in range(30)]
    plan=dict(task_ids=ids,source_manifest={'source':'hash'},upstream=str(tmp_path/'up'),image_id='fake',
        maximum_judge_calls=36,judge_task_ids=ids[:2],schedule={str(s):run.ordered_jobs(ids,s) for s in (0,1,2)})
    if e4:
        from scripts.studies.causal_experiments.e4_trial import ARMS as E4_ARMS
        plan['e4']=dict(manifest=dict(cases=[dict(task_id=t) for t in ids[:10]]))
        for seed in (0,1,2):
            plan['schedule'][str(seed)]+=[[t,a] for t in ids[:10] for a in E4_ARMS if a.startswith('e4_worker_')]
    args=SimpleNamespace(output=root,credentials=tmp_path/'credentials',estimated_cost='100')
    monkeypatch.setattr(run,'validate_execution',lambda *a:plan)
    monkeypatch.setattr(run.shared,'source_manifest',lambda:plan['source_manifest'])
    monkeypatch.setattr(run,'validate_round_inputs',lambda p:None)
    monkeypatch.setattr(run.shared,'credential',lambda *a:'synthetic')
    balance=dict(response=dict(is_available=True,balance_infos=[dict(currency='CNY',total_balance='1000')]))
    monkeypatch.setattr(run.shared,'safe_balance',lambda *a:balance)
    monkeypatch.setattr(run,'load_tasks',lambda *a:([SimpleNamespace(id=t,query='question') for t in ids],{}))
    calls=[];judge_calls=[];lock=threading.Lock();running=[0,0]
    class Process:
        def __init__(self,command,**kwargs):
            assert kwargs['cwd']==Path(run.__file__).resolve().parents[3]
            self.seed=int(command[command.index('--seed')+1]);self.task=command[command.index('--task')+1]
            self.arm=command[command.index('--arm')+1];self.done=False
            if fail:raise OSError('synthetic launch failure')
            base=root/f'round-{self.seed}'/self.task/self.arm
            with lock:
                calls.append((self.seed,self.task,self.arm));running[0]+=1;running[1]=max(running)
            if self.arm=='recon_transplant':assert (base.parent/'recon/packet.json').exists()
            if self.arm.startswith('e4_lead_'):
                assert (base.parent/self.arm.replace('e4_lead_','e4_worker_',1)/'worker-report.json').exists()
            record=dict(status='cli_exited',cleanup=dict(stopped=True),infra_degraded=infra,
                manipulation_check=dict(passed=not deviation,integrity_failure=False),
                grade=dict(status='pending_judge' if judges and self.task in ids[:2] else 'graded',score=1),
                single_agent_audit=dict(passed=True),pipeline_replay=dict(status='matched'))
            write_json(base/'result.json',record)
            write_json(base/self.task/run.session_backend(self.arm)/'report.json',record)
            if self.arm=='recon':write_json(base/'packet.json',dict(status='available',task_id=self.task,packet={}))
            if self.arm.startswith('e4_worker_'):write_json(base/'worker-report.json',dict(status='available',text='full report'))
        def wait(self,**kwargs):
            if interrupt:run.signal.getsignal(run.signal.SIGTERM)(run.signal.SIGTERM,None)
            time.sleep(.002)
            with lock:
                if not self.done:running[0]-=1;self.done=True
            return 0
        def poll(self):return 0 if self.done else None
        def terminate(self):pass
    monkeypatch.setattr(run.subprocess,'Popen',Process)
    monkeypatch.setattr(run.krama,'collect_attempt',lambda folder,record,options:record)
    def judge(**kwargs):
        with lock:judge_calls.append(kwargs)
        return dict(status='graded',score=1,attempted_calls=1)
    monkeypatch.setattr(run,'judge_once',judge)
    return args,plan,calls,judge_calls,running


def test_combined_e4_has_exactly_810_sessions_and_shared_16_slots(tmp_path,monkeypatch):
    from scripts.studies.causal_experiments import e4_report
    args,plan,calls,judges,running=execution_fixture(tmp_path,monkeypatch,e4=True)
    monkeypatch.setattr(e4_report,'worker_evaluation',lambda *a:dict(score=None,status='report_available'))
    assert run.execute(args)==0
    counts=Counter(a for _,_,a in calls)
    assert len(calls)==len(set(calls))==810
    assert sum(v for a,v in counts.items() if a.startswith('e4_worker_'))==90
    assert sum(v for a,v in counts.items() if a.startswith('e4_lead_'))==90
    assert counts['recon']==90 and all(counts[a]==90 for a in runtime.ARMS)
    assert 1<running[1]<=16
    summary=read_json(args.output/'summary.json')
    assert summary['complete'] and len(summary['grades'])==720


def test_all_three_rounds_are_interleaved_bounded_and_donor_dependent(tmp_path,monkeypatch):
    args,plan,calls,judges,running=execution_fixture(tmp_path,monkeypatch,judges=True)
    assert run.execute(args)==0
    assert len(calls)==630 and len(set(calls))==630 and len(judges)==36
    assert 1 < running[1] <= 16
    assert Counter(a for _,_,a in calls)=={a:90 for a in runtime.ROLES}
    summary=read_json(args.output/'summary.json')
    assert summary['complete'] and len(summary['grades'])==540 and summary['judge_calls']==36
    assert set(g['arm'] for g in summary['grades'])==set(runtime.ARMS)
    with pytest.raises(FileExistsError):run.execute(args)
    assert len(calls)==630


def test_launch_failure_does_not_retry_and_keeps_one_shot_marker(tmp_path,monkeypatch):
    args,_,calls,_,_=execution_fixture(tmp_path,monkeypatch,fail=True)
    with pytest.raises(OSError):run.execute(args)
    assert (args.output/'execution.json').exists() and (args.output/'failure.json').exists()
    with pytest.raises(FileExistsError):run.execute(args)
    assert not calls


def test_model_deviations_and_nonfatal_infra_do_not_truncate_assignment(tmp_path,monkeypatch):
    args,_,calls,_,_=execution_fixture(tmp_path,monkeypatch,deviation=True,infra=True)
    assert run.execute(args)==0 and len(calls)==630
    assert read_json(args.output/'summary.json')['complete']


def test_packet_metadata_never_reaches_solver_context():
    receipt=dict(status='available',packet={'task_qualifiers':['dates'],'candidate_sources':[],'uncertainties':[]},
                 task_id='legal-easy-4',donor_session_id='private-session',origin='recon')
    adapter=runtime.StudyAdapter('recon_transplant','fake','public question',receipt)
    text=runtime.packet_text(adapter.packet)
    assert 'legal-easy-4' not in text and 'private-session' not in text and 'task_id' not in text


def test_transplant_checks_the_actual_prompt(tmp_path):
    observer=tmp_path/'native-profile/observer';observer.mkdir(parents=True)
    (observer/'events.jsonl').write_text('')
    packet=dict(status='unavailable',packet=None)
    (tmp_path/'cli').mkdir();p=tmp_path/'cli/prompt.txt';p.write_text('not injected')
    assert runtime.manipulation_check(tmp_path,'recon_transplant',packet)['integrity_failure']
    p.write_text('task\n'+runtime.packet_text(packet))
    assert runtime.manipulation_check(tmp_path,'recon_transplant',packet)['passed']


def test_interruption_prevents_later_rounds(tmp_path,monkeypatch):
    args,_,calls,_,_=execution_fixture(tmp_path,monkeypatch,interrupt=True)
    assert run.execute(args)==1
    assert calls and {s for s,t,a in calls}=={0}
    assert not read_json(args.output/'summary.json')['complete']


def test_five_arm_report_preserves_missing_scores_and_shared_cohort():
    ids=['a','b'];plan=dict(task_ids=ids)
    grades=[dict(seed=s,task_id=t,arm=a,score=1 if a=='native' else 0,
        native_audit=dict(passed=True),manipulation_check=dict(passed=True)) for s in (0,1,2) for t in ids for a in runtime.ARMS]
    result=report.summarize(plan,grades)
    assert next(r for r in result['raw_intention_to_treat']['contrasts'] if r['treatment']=='native')['mean_difference']==1
    grades[0]['score']=None;grades[0]['native_audit']['passed']=False
    result=report.summarize(plan,grades)
    assert result['raw_intention_to_treat']['groups'][0]['mean'] is None
    assert result['paired_protocol_sensitivity']['excluded_tasks']==['a']
    assert all(g['tasks_per_round']==1 for g in result['paired_protocol_sensitivity']['groups'])
    with pytest.raises(ValueError):report.summarize(plan,grades+[grades[0]])


def test_exact_sign_flip_and_holm_for_thirty_task_analysis():
    from itertools import product
    values=[.2,-.1,.4,.3]
    brute=sum(abs(sum(a*b for a,b in zip(s,values)))>=abs(sum(values))-1e-12
              for s in product((-1,1),repeat=len(values)))/2**len(values)
    assert report.sign_flip(values)==brute
    assert report.sign_flip([1]*30)==pytest.approx(2/2**30)
    assert report.holm([.01,.04,.03,.2])==pytest.approx([.04,.09,.09,.2])


def test_thirty_question_extension_is_outcome_blind_and_reproducible(tmp_path,monkeypatch):
    from scripts.studies.causal_experiments import selection
    from benchmarks.kramabench.tasks import Task
    pool=[Task(f'archeology-easy-{i}','archeology',f'Public question {i}') for i in range(50)]
    base=[dict(task_id=t.id,task_sha256=selection.task_fingerprint('kramabench',t)) for t in pool[:20]]
    monkeypatch.setattr(selection,'load_tasks',lambda *a:(pool,{}))
    monkeypatch.setattr(selection,'read_json',lambda *a:dict(benchmarks=dict(kramabench=base)))
    a,manifest=selection.selected_tasks(tmp_path)
    pool.reverse()
    b,_=selection.selected_tasks(tmp_path)
    assert a==b and len(a)==30 and len({t.id for t in a})==30
    assert [t.id for t in a[:20]]==[r['task_id'] for r in base]
    assert manifest['sampling_seed']==20261112


def test_next_seed_starts_before_a_long_tail_finishes(tmp_path,monkeypatch):
    args,plan,calls,_,_=execution_fixture(tmp_path,monkeypatch)
    original=run.subprocess.Popen
    next_seed=threading.Event()
    slow_task,slow_arm=plan['schedule']['0'][0]
    class SlowProcess(original):
        def __init__(self,*values,**kwargs):
            super().__init__(*values,**kwargs)
            if self.seed==1:next_seed.set()
        def wait(self,**kwargs):
            if (self.seed,self.task,self.arm)==(0,slow_task,slow_arm):
                assert next_seed.wait(10), 'Round barrier left the free slots idle'
            return super().wait(**kwargs)
    monkeypatch.setattr(run.subprocess,'Popen',SlowProcess)
    assert run.execute(args)==0
    assert next_seed.is_set() and len(calls)==len(set(calls))==630


@pytest.mark.parametrize('flag',['--continue-frozen-source','--superseded-controller-pid'])
def test_retired_handoff_flags_cannot_bypass_one_shot_admission(tmp_path,monkeypatch,flag):
    monkeypatch.setattr(run,'execute',lambda *a:pytest.fail('Retired handoff reached execution'))
    with pytest.raises(SystemExit) as error:
        run.main(['--output',str(tmp_path),'--proof',str(tmp_path/'proof'),
                  '--execute',flag,'123'])
    assert error.value.code==2


def test_existing_execution_marker_blocks_before_reading_credentials(tmp_path,monkeypatch):
    write_json(tmp_path/'execution.json',{})
    monkeypatch.setattr(run.shared,'credential',lambda *a:pytest.fail('Repeated execution read credentials'))
    with pytest.raises(FileExistsError,match='One-shot'):
        run.execute(SimpleNamespace(output=tmp_path))
