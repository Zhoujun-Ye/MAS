"""Prepare/review/freeze the six-arm thirty-task study; no implicit paid dispatch."""

import argparse
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from benchmarks.kramabench.evaluation import grade_answer
from benchmarks.kramabench.semantic_judge import judge_once
from benchmarks.kramabench.tasks import load_tasks
from common.io import fingerprint, read_json, write_json
from common.journal import Journal, exclusive
from harness.runtime_support import runtime as shared
from harness.runtime_support.admission import (BalanceWatch, admit_balance, fatal_provider_record,
                                               infrastructure_health)
from scripts.kramabench import cli_runtime as krama
from scripts.studies.benchmark_matrix import cleanup_owned_containers
from .selection import selected_tasks
from .runtime import ARMS, ROLES, RECON, SELF_BRIEF, backend_for
from .hooks import NULL_REQUEST
from . import e4_trial, e4_prepare

SOLVERS, RECONS = 540, 90


def session_backend(arm):
    return e4_trial.backend_for(arm) if arm in e4_trial.ARMS else backend_for(arm)


def session_counts(plan):
    extra=180 if plan.get('e4') else 0
    return SOLVERS+RECONS+extra,SOLVERS+extra


def dependent_arm(arm):
    if arm=='recon':return 'recon_transplant'
    if arm.startswith('e4_worker_') and arm in e4_trial.ARMS:
        return arm.replace('e4_worker_','e4_lead_',1)
    return None


def e4_scope(args,binding,ids):
    path=getattr(args,'e4_manifest',None)
    if not path:return None
    manifest=e4_prepare.validate(read_json(path))
    proof_path=getattr(args,'e4_proof',None)
    proof=read_json(proof_path) if proof_path else None
    expected={f"lead-{c['task_id']}-verbatim" for c in manifest['cases']}
    for role in ('Explore','general-purpose'):
        task=next(c['task_id'] for c in manifest['cases'] if c['prefix']['agent_type']==role)
        expected.update(f'worker-{task}-{v}' for v in ('verbatim','open','task_only'))
    if (not proof or proof.get('passed') is not True or proof.get('paid_calls')!=0
            or proof.get('runtime_binding')!=binding or proof.get('source_manifest')!=shared.source_manifest()
            or proof.get('manifest_sha256')!=fingerprint(manifest)
            or set(proof.get('checks',{}))!=expected
            or any(c.get('passed') is not True for c in proof['checks'].values())
            or any(c['task_id'] not in ids for c in manifest['cases'])):
        raise ValueError('Fresh E4 source-bound native role/resume proofs are required')
    return dict(manifest=manifest,manifest_path=str(path.resolve()),manifest_sha256=sha(path),
        proof_path=str(proof_path.resolve()),proof_sha256=sha(proof_path),worker_sessions=90,lead_sessions=90)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ordered_jobs(ids, seed):
    tasks = sorted(ids, key=lambda t: hashlib.sha256(f'{seed}:{t}'.encode()).hexdigest())
    return [[t, arm] for t in tasks for arm in sorted(
        [a for a in ROLES if a != 'recon_transplant'],
        key=lambda a: hashlib.sha256(f'{seed}:{t}:{a}'.encode()).hexdigest())]


def build_plan(args):
    selected,manifest = selected_tasks(args.root)
    ids = [t.id for t in selected]
    if len(ids)!=30 or len(set(ids))!=30:
        raise ValueError('Require the frozen thirty-task comparison')
    eligible = [t.id for t in selected if grade_answer(args.root/'kramabench/upstream',t.id,None)['answer_type']=='string_approximate']
    judges=len(eligible)*len(ARMS)*3
    image=json.loads(subprocess.check_output(['docker','image','inspect',args.image]))[0]['Id']
    proof=read_json(args.proof)
    binding=dict(image_id=image,binary_sha256=sha(shared.CLAUDE))
    if (not proof or proof.get('passed') is not True or proof.get('paid_calls') != 0
            or proof.get('runtime_binding') != binding or proof.get('source_manifest') != shared.source_manifest()
            or set(proof.get('roles',{})) != set(ROLES)
            or any(v.get('passed') is not True for v in proof['roles'].values())):
        raise ValueError('Fresh source/image/binary-bound free proofs for all six roles are required')
    if (os.cpu_count() or 0) < 16*8:
        raise ValueError('Host lacks the authorized CPU reservations')
    inventory=krama.verify_inputs(args.root/'kramabench/upstream')
    plan=dict(kind='native-single-causal30-v2', task_ids=ids, seeds=[0,1,2], arms=list(ARMS),
        solver_attempts=SOLVERS,independent_recon_attempts=RECONS,maximum_judge_calls=judges,
        judge_task_ids=eligible,retries=0,solver_concurrency=16,judge_concurrency=2,
        cpu_per_attempt=8,compute_threads=4,shared_compute_slots=16,
        timeout_seconds=3600,replay_timeout_seconds=180,inference_policy=shared.inference_configuration(),
        upstream=str((args.root/'kramabench/upstream').resolve()),
        task_manifest=manifest,task_manifest_sha256=fingerprint(manifest),inputs_sha256=fingerprint(inventory),
        source_manifest=shared.source_manifest(),image_id=image,binary_sha256=binding['binary_sha256'],
        free_proof=dict(path=str(args.proof.resolve()),sha256=sha(args.proof)),
        intervention_prompts=dict(recon=RECON,self_brief=SELF_BRIEF,null_worker=NULL_REQUEST),
        null_worker_tool_policy='Preserve native definitions and lead context; deny every worker tool execution, do not hide tool definitions',
        schedule={str(s):ordered_jobs(ids,s) for s in (0,1,2)},
        round_scheduling='Work-conserving across seeds; retain within-seed order and same-seed donor dependencies',
        budget_policy=dict(currency='CNY',monetary_cap=None,balance_reserve='5',safety_factor='1.5'),
        estimands=dict(null_worker='Total Native package after replacing every delegated request/report with an empty no-tool worker; not a unique mediation decomposition',
            recon_transplant='Availability of an independent untrusted report plus its delivery context; donor compute/cost is additional',
            self_brief='Compare self_brief against brief_prompt for the incremental enforcement effect, and brief_prompt against Single for the instruction effect'),
        halt_policy=dict(continue_without_retry=['nonfatal upstream 5xx','transport failure with known terminal session','null report formatting deviation','brief not exercised','invalid donor after native Stop feedback'],
                         stop=['credential failure','confirmed leak','policy/integrity failure','unknown dispatch','cleanup failure','harness replay failure','operator stop','balance reserve']),
        analysis=dict(primary_contrast=['null_worker','native'],
            secondary_contrasts=[['native','single'],['recon_transplant','single'],['self_brief','brief_prompt'],['brief_prompt','single']],
            unit='task cluster; average the three repeats within each task before paired contrasts',
            primary_metric='all thirty assigned tasks, equal-weight mean answer score; no post-outcome exclusions',
            inference='two-sided exact task-level sign-flip p and task-cluster bootstrap 95% CI; primary alpha=0.05',
            numeric_tolerance=1e-12,
            secondary_testing='Holm correction across secondary task-sign-flip p-values; exploratory mechanism evidence',
            decision_rule='A primary CI excluding zero and p<0.05 supports a difference in the null-worker intervention package, not unique mediation. A CI including zero is inconclusive, not equivalence.',
            equivalence='No equivalence claim or near-Native classification is preregistered; 30 tasks may still be underpowered.',
            missing='Terminal failures without usable submissions score zero under benchmark rules; unknown execution or judge outcomes remain unknown. Never drop cells or retry.',
            secondary_outcomes=['non-submission rate','delegation call count','elapsed time from first emitted worker report to first observed lead submission write; unknown if no observable write'],
            packet_availability='report available donors / all ninety assigned donors; unavailable donors retained in E2 intention-to-treat'),
        limitations=['Only Native and Single, never Structured.',
            'Seeds determine dispatch order, not provider sampling.',
            'Report schema checks do not certify semantic correctness or absence of derived answers.',
            'No retries, best-of-N, automatic report repair, or historical-score replacement.',
            'Thirty task clusters with three stochastic repetitions, not ninety independent questions.',
            'Failed recon produces an explicit unavailable receipt; E2 still runs once and remains in intention-to-treat reporting.'])
    e4=e4_scope(args,binding,ids)
    if e4:
        plan['e4']=e4
        plan['kind']='native-single-causal30-e4-t07-v1'
        plan['total_new_sessions']=810
        for seed in (0,1,2):
            additions=[[c['task_id'],a] for c in e4['manifest']['cases'] for a in e4_trial.ARMS if a.startswith('e4_worker_')]
            plan['schedule'][str(seed)] = sorted(plan['schedule'][str(seed)]+additions,
                key=lambda x:hashlib.sha256(f'{seed}:{x[0]}:{x[1]}'.encode()).hexdigest())
    return plan


def prepare(args):
    if args.output.exists():
        raise ValueError('Use a fresh study output')
    plan=build_plan(args)
    args.output.mkdir(parents=True,mode=0o700)
    write_json(args.output/'plan.json',plan)
    write_json(args.output/'task-manifest.json',plan['task_manifest'])
    write_json(args.output/'prepared.json',dict(plan_sha256=fingerprint(plan),paid_calls=0,review_required=True))
    return plan


def validate_execution(args):
    if (args.output/'execution.json').exists():
        raise FileExistsError('One-shot study execution already claimed; no automatic continuation')
    plan=read_json(args.output/'plan.json')
    if (not args.review_confirmed or args.reviewed_plan_sha256 != fingerprint(plan)
            or args.authorized_solvers != SOLVERS or args.authorized_recons != RECONS
            or args.authorized_judges != plan.get('maximum_judge_calls')):
        raise ValueError('Review confirmation, exact plan hash and exact 540/90/judge authorization are required')
    if plan.get('e4') and getattr(args,'authorized_e4_sessions',None)!=180:
        raise ValueError('Exact authorization for 180 additional E4 sessions is required')
    if not plan or plan != build_plan(args):
        raise ValueError('Prepared source, assets, runtime, proof or scope changed')
    if read_json(args.output/'prepared.json')['plan_sha256'] != fingerprint(plan):
        raise ValueError('Prepared plan changed')
    if read_json(args.output/'task-manifest.json') != plan['task_manifest']:
        raise ValueError('Frozen task manifest changed')
    if not args.estimated_cost:
        raise ValueError('A positive remaining-scope cost estimate is required for balance admission')
    return plan


def validate_round_inputs(plan):
    if (shared.source_manifest()!=plan['source_manifest'] or fingerprint(selected_tasks(Path(plan['upstream']).parents[1])[1])!=plan['task_manifest_sha256']
            or sha(Path(plan['free_proof']['path']))!=plan['free_proof']['sha256']
            or sha(shared.CLAUDE)!=plan['binary_sha256']
            or fingerprint(krama.verify_inputs(Path(plan['upstream'])))!=plan['inputs_sha256']):
        raise ValueError('Frozen source, proof, binary, tasks or inputs changed between rounds')
    if plan.get('e4'):
        e4=plan['e4']
        if sha(Path(e4['manifest_path']))!=e4['manifest_sha256'] or sha(Path(e4['proof_path']))!=e4['proof_sha256']:
            raise ValueError('Frozen E4 manifest or proof changed')


def execute(args):
    plan=validate_execution(args)
    root=args.output
    trial_source=Path(__file__).resolve().parents[3]
    key=shared.credential(args.credentials)
    current=shared.safe_balance(key,root,'balance-before')
    before=current
    admission=admit_balance(current,'CNY',args.estimated_cost,'1.5','5')
    tasks={t.id:t for t in load_tasks(Path(plan['upstream']))[0]}
    stop,done=threading.Event(),threading.Event()
    lock=threading.Lock(); active=set(); rows=[]; grades=[]; claims=0
    compute=threading.BoundedSemaphore(16)
    watch=BalanceWatch(lambda:shared.safe_balance(key,root,'balance-current'),'CNY','5',initial=current)
    journal=Journal(root/'phases.sqlite')
    binding=fingerprint(plan)

    def interrupt(signum, frame):
        stop.set()
        with lock:
            for p in active:
                if p.poll() is None:p.terminate()

    def checked(function, *values):
        try:
            return function(*values)
        except BaseException:
            interrupt(None,None)
            raise

    def monitor():
        observed={}
        while not done.wait(1):
            try:
                watch.check()
                for path in root.glob('round-*/*/*/*/claude-code-*/gateway-requests.jsonl'):
                    stamp=path.stat().st_mtime_ns
                    if observed.get(path)==stamp:continue
                    observed[path]=stamp
                    if fatal_provider_record(path):
                        write_json(root/'fatal-provider-error.json',dict(evidence=str(path),at=shared.now()))
                        interrupt(None,None)
                    elif infrastructure_health(path)['infra_degraded'] is True:
                        write_json(root/'infrastructure-observations.json',dict(evidence=str(path),at=shared.now(),policy='Record and continue the assigned scope; zero retries'))
            except Exception as error:
                stop.set()
                write_json(root/'monitor-error.json',dict(error_type=type(error).__name__,at=shared.now()))

    def solve(seed,task,arm):
        identity=(seed,task,arm)
        base=root/f'round-{seed}'/task/arm
        initial=dict(seed=seed,task_id=task,arm=arm,status='dispatch_unknown',output=str(base))
        journal.claim('session',identity,binding,initial)
        if stop.is_set():
            result=dict(initial,status='not_started');journal.finish('session',identity,binding,result);return result
        module='e4_trial' if arm in e4_trial.ARMS else 'trial'
        command=[sys.executable,'-m','scripts.studies.causal_experiments.'+module,'--plan',str(root/'plan.json'),
                 '--seed',str(seed),'--task',task,'--arm',arm,'--credentials',str(args.credentials),'--execute']
        with compute:
            if stop.is_set():
                result=dict(initial,status='not_started');journal.finish('session',identity,binding,result);return result
            watch.check()
            log=root/'logs'/f'{seed}-{task}-{arm}.log';log.parent.mkdir(exist_ok=True)
            with log.open('x') as stream:
                env={name:os.environ[name] for name in ('PATH','HOME','LANG') if name in os.environ}
                with lock:
                    if stop.is_set():
                        result=dict(initial,status='not_started');journal.finish('session',identity,binding,result);return result
                    p=subprocess.Popen(command,stdout=stream,stderr=subprocess.STDOUT,env=env,cwd=trial_source)
                    active.add(p)
                try:
                    try:code=p.wait(timeout=4200)
                    except subprocess.TimeoutExpired:
                        p.terminate()
                        try:code=p.wait(timeout=30)
                        except subprocess.TimeoutExpired:p.kill();code=p.wait(timeout=10)
                        cleanup_owned_containers(base)
                        stop.set()
                finally:
                    with lock:active.discard(p)
        report=read_json(base/'result.json',{})
        result=dict(initial,status=report.get('status','dispatch_unknown'),returncode=code,
                    infra_degraded=report.get('infra_degraded'),manipulation_check=report.get('manipulation_check'))
        if (result['status']=='dispatch_unknown'
                or report.get('cleanup',{}).get('stopped') is not True
                or report.get('manipulation_check',{}).get('integrity_failure') is True):
            stop.set()
            with lock:
                write_json(root/'dispatch-paused.json',dict(identity=identity,result=result,at=shared.now()))
        journal.finish('session',identity,binding,result)
        return result

    def grade(row):
        nonlocal claims
        seed,task,arm=row['seed'],row['task_id'],row['arm']
        identity=(seed,task,arm)
        journal.claim('grade',identity,binding,dict(status='grading_unknown'))
        folder=Path(row['output'])/task/session_backend(arm)
        report=read_json(folder/'report.json')
        if arm.startswith('e4_worker_'):
            from .e4_report import worker_evaluation
            result=dict(seed=seed,task_id=task,arm=arm,judge_calls=0,
                **worker_evaluation(Path(row['output']),Path(plan['upstream']),task))
        elif not report or report.get('cleanup',{}).get('stopped') is not True:
            result=dict(seed=seed,task_id=task,arm=arm,status='grading_unavailable',score=None,judge_calls=0)
        else:
            with compute:
                options=SimpleNamespace(upstream=Path(plan['upstream']),image=plan['image_id'],cpus=8,compute_threads=4,replay_timeout=180)
                report=krama.collect_attempt(folder,report,options)
            result=dict(seed=seed,task_id=task,arm=arm,status=report['grade']['status'],score=report['grade']['score'],
                judge_calls=0,native_audit=report.get('single_agent_audit',report.get('subagents_audit')),
                manipulation_check=report.get('manipulation_check'),pipeline_replay=report.get('pipeline_replay'))
            if report['grade']['status']=='pending_judge':
                if task not in plan['judge_task_ids']:
                    raise ValueError('Unexpected semantic judge task')
                if not stop.is_set():
                    watch.check()
                    with lock:
                        if claims>=plan['maximum_judge_calls']:raise ValueError('Authorized judge slots exhausted')
                        claims+=1
                    judged=judge_once(upstream=Path(plan['upstream']),task_id=task,backend=arm,
                        submission_path=folder/'submission.json',question=tasks[task].query,key=key,
                        output=root/'grades'/f'round-{seed}'/task/arm)
                    result.update(status=judged['status'],score=judged['score'],judge_calls=judged['attempted_calls'])
                    if judged.get('fatal'):interrupt(None,None)
            if (report.get('pipeline_replay') or {}).get('status') == 'harness_error':
                stop.set()
        journal.finish('grade',identity,binding,result)
        return result

    with exclusive(root/'controller.lock'):
        with (root/'execution.json').open('x') as stream:
            json.dump(dict(plan_sha256=binding,started_at=shared.now(),authorized_solvers=SOLVERS,
                authorized_recons=RECONS,authorized_e4_sessions=180 if plan.get('e4') else 0,
                authorized_judges=plan['maximum_judge_calls'],balance_admission=admission,review_confirmed=True),stream)
        previous={s:signal.signal(s,interrupt) for s in (signal.SIGTERM,signal.SIGINT)}
        watcher=threading.Thread(target=monitor,daemon=True);watcher.start()
        try:
            with ThreadPoolExecutor(max_workers=16) as solvers, ThreadPoolExecutor(max_workers=2) as graders:
                solving={};grading=set()
                ready=deque()
                for seed in (0,1,2):
                    if stop.is_set():break
                    validate_round_inputs(plan)
                    ready.extend((seed,t,a) for t,a in plan['schedule'][str(seed)])
                while ready or solving or grading:
                    while ready and len(solving)<16 and not stop.is_set():
                        seed,task,arm=ready.popleft()
                        f=solvers.submit(checked,solve,seed,task,arm);solving[f]=(seed,task,arm)
                    if not solving and not grading:break
                    finished,_=wait(set(solving)|grading,return_when=FIRST_COMPLETED)
                    for f in finished:
                        if f in solving:
                            seed,task,arm=solving.pop(f);row=f.result();rows.append(row)
                            dependency=dependent_arm(arm)
                            if dependency and row['status'] not in {'not_started','dispatch_unknown'}:
                                ready.appendleft((seed,task,dependency))
                            if arm!='recon' and row['status'] not in {'not_started','dispatch_unknown'}:
                                grading.add(graders.submit(checked,grade,row))
                        else:
                            grading.remove(f);grades.append(f.result())
                    active_seeds=sorted({ident[0] for ident in solving.values()})
                    write_json(root/'progress.json',dict(active_seed=active_seeds[0] if len(active_seeds)==1 else None,
                        active_seeds=active_seeds,completed_sessions=len(rows),
                        completed_solvers=sum(r['arm'] in ARMS for r in rows),completed_recons=sum(r['arm']=='recon' for r in rows),
                        completed_e4_workers=sum(r['arm'].startswith('e4_worker_') for r in rows),
                        completed_e4_leads=sum(r['arm'].startswith('e4_lead_') for r in rows),
                        completed_grades=len(grades),judge_calls=claims,paused=stop.is_set(),at=shared.now()))
            after=shared.safe_balance(key,root,'balance-after')
            write_json(root/'summary.json',dict(plan_sha256=binding,rows=rows,grades=grades,judge_calls=claims,
                complete=(len(rows),len(grades))==session_counts(plan) and not stop.is_set(),
                account_delta=shared.observed_balance_deltas(before,after),
                accounting_scope='Host request ledgers and shared-account interval; unknown partial billing is not zero',finished_at=shared.now()))
        except BaseException as error:
            interrupt(None,None)
            write_json(root/'failure.json',dict(error_type=type(error).__name__,at=shared.now()))
            raise
        finally:
            done.set();watcher.join()
            if stop.is_set():cleanup_owned_containers(root)
            for s,h in previous.items():signal.signal(s,h)
    return 0 if (len(rows),len(grades))==session_counts(plan) and not stop.is_set() else 1


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path('/home/zhoujunye/mas-data'))
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--image',default=shared.DEFAULT_SOLVER_IMAGE)
    p.add_argument('--proof',type=Path,required=True)
    p.add_argument('--e4-manifest',type=Path);p.add_argument('--e4-proof',type=Path)
    p.add_argument('--authorized-e4-sessions',type=int)
    p.add_argument('--credentials',type=Path,default=Path('/home/zhoujunye/mas/.env'))
    mode=p.add_mutually_exclusive_group()
    mode.add_argument('--prepare',action='store_true');mode.add_argument('--execute',action='store_true')
    p.add_argument('--review-confirmed',action='store_true')
    p.add_argument('--reviewed-plan-sha256')
    p.add_argument('--authorized-solvers',type=int);p.add_argument('--authorized-recons',type=int)
    p.add_argument('--authorized-judges',type=int);p.add_argument('--estimated-cost')
    args=p.parse_args(argv)
    for key in ('root','output','proof','credentials'):setattr(args,key,getattr(args,key).resolve())
    if args.execute:return execute(args)
    if not args.prepare:
        print(json.dumps(dict(status='planned',solvers=SOLVERS,independent_recons=RECONS,
            maximum_judges='actual eligible tasks x six arms x three rounds',solver_concurrency=16,judge_concurrency=2,seeds=[0,1,2],paid_calls=0,review_required=True)))
        return 0
    plan=prepare(args);print(json.dumps(dict(status='prepared',plan_sha256=fingerprint(plan),paid_calls=0,review_required=True)))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
