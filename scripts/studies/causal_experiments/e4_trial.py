"""A single authorized E4 worker replay or its paired native lead continuation."""

import argparse
import json
from pathlib import Path
import signal
import threading
from types import SimpleNamespace

from benchmarks.kramabench.tasks import load_tasks
from common.io import fingerprint, read_json, write_json
from common.journal import Journal
from harness.runtime_support import runtime as shared
from scripts.kramabench import cli_runtime as krama
from .e4_runtime import VARIANTS, factory

ARMS=tuple(f'e4_{phase}_{v}' for phase in ('worker','lead') for v in VARIANTS)


def parts(arm):
    if arm not in ARMS:raise ValueError('Unknown E4 arm')
    _,phase,variant=arm.split('_',2)
    return phase,variant


def backend_for(arm):
    return 'claude-code-single-agent' if parts(arm)[0]=='worker' else 'claude-code-subagents'


def attempt(task,case,phase,variant,output,upstream,image,key,*,report_text=None,timeout=900):
    options=SimpleNamespace(output=output,upstream=upstream,image=image,timeout=timeout,
        effort='none',cpus=8,compute_threads=4,record_resources=True,
        subagents_prompt='structured' if phase=='worker' else 'native')
    backend='claude-code-single-agent' if phase=='worker' else 'claude-code-subagents'
    result=krama.run_attempt(task,backend,options,key,threading.Event(),set(),threading.Lock(),
        adapter_factory=factory(case,phase,variant,report_text))
    if result.get('cleanup',{}).get('stopped') is not True:
        raise ValueError('E4 replay failed to quiesce')
    folder=output/task.id/backend
    check=result.get('cli',{}).get('e4_replay',{})
    result['manipulation_check']=dict(passed=bool(check),integrity_failure=not bool(check),
        phase=phase,variant=variant,source_prefix_sha256=case['prefix']['provenance']['prefix_sha256'])
    result['e4']=dict(phase=phase,variant=variant,premise_strength=case['premise_strength'],
        premise_origin=case['premise_origin'],native_baseline_audit_applicable=False,
        native_baseline_status=result['status'])
    if phase=='lead' and result['status']=='native_condition_unverified' and result.get('cli',{}).get('status')=='cli_exited':
        result['status']='cli_exited'  # The already-recorded delegation is outside this continuation's hooks.
    if phase=='worker':
        raw=result.get('cli',{}).get('native_result',{}).get('result')
        available=result.get('cli',{}).get('status')=='cli_exited' and isinstance(raw,str) and bool(raw.strip())
        # Forward the entire observed report, including malformed reports; never select or repair it.
        receipt=dict(status='available' if available else 'unavailable',text=raw if available else
            'The delegated worker did not return a completed report. No report is available.',
            raw_result=raw,source_prefix_sha256=case['prefix']['provenance']['prefix_sha256'],
            task_id=task.id,variant=variant)
        write_json(output/'worker-report.json',receipt)
        result['e4_worker_receipt']=receipt
    write_json(folder/'report.json',result)
    write_json(output/'result.json',result)
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan',type=Path,required=True);p.add_argument('--credentials',type=Path,required=True)
    p.add_argument('--seed',type=int,choices=(0,1,2),required=True)
    p.add_argument('--task',required=True);p.add_argument('--arm',choices=ARMS,required=True)
    p.add_argument('--execute',action='store_true');args=p.parse_args(argv)
    if not args.execute:print(json.dumps(dict(status='planned',paid_calls=0)));return 0
    plan=read_json(args.plan);binding=fingerprint(plan)
    marker=read_json(args.plan.parent/'execution.json',{})
    claim=Journal(args.plan.parent/'phases.sqlite').get('session',(args.seed,args.task,args.arm))
    if (shared.source_manifest()!=plan['source_manifest'] or marker.get('plan_sha256')!=binding
            or marker.get('review_confirmed') is not True or not claim
            or claim['state']!='claimed' or claim['binding']!=binding):
        raise ValueError('Missing frozen, authorized one-shot E4 dispatch')
    case=next(c for c in plan['e4']['manifest']['cases'] if c['task_id']==args.task)
    task=next(t for t in load_tasks(Path(plan['upstream']))[0] if t.id==args.task)
    phase,variant=parts(args.arm);root=args.plan.parent/f'round-{args.seed}'/args.task
    text=None
    if phase=='lead':
        worker=root/f'e4_worker_{variant}'
        receipt=read_json(worker/'worker-report.json')
        if (not receipt or receipt!=read_json(worker/'result.json',{}).get('e4_worker_receipt')
                or receipt['source_prefix_sha256']!=case['prefix']['provenance']['prefix_sha256']):
            raise ValueError('Paired E4 report binding failed')
        text=receipt['text']
    def interrupted(signum,frame):raise KeyboardInterrupt('E4 interrupted; no retry')
    previous=signal.signal(signal.SIGTERM,interrupted)
    try:
        result=attempt(task,case,phase,variant,root/args.arm,Path(plan['upstream']),plan['image_id'],
                       shared.credential(args.credentials),report_text=text)
    finally:signal.signal(signal.SIGTERM,previous)
    print(json.dumps(dict(task_id=args.task,arm=args.arm,status=result['status'])))
    return 0 if result.get('cli',{}).get('status')=='cli_exited' else 1


if __name__=='__main__':raise SystemExit(main())
