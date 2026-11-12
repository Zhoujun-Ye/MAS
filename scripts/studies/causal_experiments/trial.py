"""One isolated native causal-study session; never retry or implicitly dispatch."""

import argparse
import json
from pathlib import Path
import signal
import sys
import threading
import tempfile
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from common.io import fingerprint, read_json, write_json
from common.journal import Journal
from harness.runtime_support import runtime as shared
from benchmarks.kramabench.tasks import load_tasks
from scripts.kramabench import cli_runtime as krama
from .runtime import ROLES, backend_for, factory, manipulation_check, recon_packet, solver_packet


def attempt(task, arm, output, upstream, image, key, *, packet=None, timeout=3600):
    options = SimpleNamespace(output=output, upstream=upstream, image=image, timeout=timeout,
        effort='none', cpus=8, compute_threads=4, record_resources=True, subagents_prompt='native')
    backend = backend_for(arm)
    if backend.endswith('single-agent'):
        options.subagents_prompt = 'structured'  # Selects the unchanged Single prompt, not Structured runtime.
    stop, active, lock = threading.Event(), set(), threading.Lock()
    with tempfile.TemporaryDirectory(prefix='mas-causal-policy-') as private:
        private=Path(private)
        config=private/'policy.json';write_json(config,dict(arm=arm))
        mounts=[(config,'/causal/policy.json'),(Path(__file__).with_name('hooks.py'),'/causal/hooks.py'),
                (Path(__file__).with_name('packet_validation.py'),'/causal/packet_validation.py')]
        report = krama.run_attempt(task, backend, options, key, stop, active, lock,
            adapter_factory=factory(arm, task.query, packet),readonly_mounts=mounts)
    folder = output/task.id/backend
    if report.get('cleanup', {}).get('stopped') is not True:
        raise ValueError('Study solver did not quiesce')
    if arm == 'recon':
        report['manipulation_check']=manipulation_check(folder,arm)
        try:
            if report['status'] != 'cli_exited':
                raise ValueError('Recon session did not complete')
            packet = recon_packet(folder, upstream)
            packet_receipt = dict(status='available', task_id=task.id, packet=packet,
                origin='independent_recon', lead_workspace_access=False,
                donor_session_id=report.get('cli',{}).get('native_result',{}).get('session_id'))
        except (OSError, ValueError, TypeError, KeyError) as error:
            packet_receipt = dict(status='unavailable', task_id=task.id, packet=None,
                error_type=type(error).__name__, no_retry=True)
        write_json(output/'packet.json', packet_receipt)
        report['recon_receipt'] = packet_receipt
    else:
        report['manipulation_check'] = manipulation_check(folder, arm, packet)
    report['causal_arm'] = arm
    write_json(folder/'report.json', report)
    write_json(output/'result.json', report)
    return report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--seed', type=int, required=True, choices=(0,1,2))
    p.add_argument('--task', required=True)
    p.add_argument('--arm', required=True, choices=ROLES)
    p.add_argument('--credentials', type=Path, required=True)
    p.add_argument('--execute', action='store_true')
    args=p.parse_args(argv)
    if not args.execute:
        print(json.dumps(dict(status='planned', paid_calls=0))); return 0
    plan=read_json(args.plan)
    if plan['source_manifest'] != shared.source_manifest():
        raise ValueError('Frozen study source changed')
    marker=read_json(args.plan.parent/'execution.json',{})
    claim=Journal(args.plan.parent/'phases.sqlite').get('session',(args.seed,args.task,args.arm))
    if (marker.get('plan_sha256') != fingerprint(plan) or marker.get('review_confirmed') is not True
            or not claim or claim['state']!='claimed' or claim['binding'] != fingerprint(plan)):
        raise ValueError('No authorized one-shot study dispatch marker')
    tasks={t.id:t for t in load_tasks(Path(plan['upstream']))[0]}
    if args.task not in plan['task_ids']:
        raise ValueError('Task outside frozen study scope')
    root=args.plan.parent/f'round-{args.seed}'/args.task
    packet=None
    if args.arm=='recon_transplant':
        receipt=read_json(root/'recon/packet.json')
        if receipt is None or receipt.get('task_id')!=args.task:
            raise ValueError('Same-task/same-round donor receipt missing')
        donor=read_json(root/'recon/result.json',{})
        if receipt != donor.get('recon_receipt'):
            raise ValueError('Frozen donor packet changed')
        packet=solver_packet(receipt)
    def interrupted(signum, frame):
        raise KeyboardInterrupt('Study session interrupted; no retry')
    previous = signal.signal(signal.SIGTERM, interrupted)
    try:
        report=attempt(tasks[args.task], args.arm, root/args.arm, Path(plan['upstream']),plan['image_id'],
            shared.credential(args.credentials),packet=packet)
    finally:
        signal.signal(signal.SIGTERM, previous)
    print(json.dumps(dict(task_id=args.task,arm=args.arm,status=report['status'])))
    return 0 if report['status']=='cli_exited' else 1


if __name__=='__main__':
    raise SystemExit(main())
