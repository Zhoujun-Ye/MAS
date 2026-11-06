"""Run existing matrix workflows on the frozen Validation20 evidence pair."""

import argparse
import json
import os
from pathlib import Path
from types import SimpleNamespace

from common.io import write_json
from harness.runtime_support.runtime import now
from scripts.studies import benchmark_matrix
from scripts.studies.matched_matrix_report import collect, timeout_zero, write_report

ROOT=Path(__file__).resolve().parents[2]
MANIFEST=ROOT/'docs/studies/validation20-v1-manifest.json'
MANIFEST_SHA='fc39ad8539e2af0b140a6b9a8b3144d241742b2c3b2424b6d74ae03f1829e0a5'


def settings():
    return benchmark_matrix.protocol_settings(SimpleNamespace(effort='high',backends=['observations','full'],
        organization_prompt=None,concurrency=6,judge_concurrency=2))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--proofs',type=Path,required=True)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--retain-started-from',type=Path)
    args=parser.parse_args(argv)
    if benchmark_matrix.digest(MANIFEST)!=MANIFEST_SHA:
        raise ValueError('Frozen Validation20 manifest changed')
    output=args.output.resolve()
    plan=dict(attempts=120,maximum_judge_calls=106,monetary_cap=None,retries=0,
        output=str(output),task_manifest_sha256=MANIFEST_SHA,protocol_settings=settings(),
        modes=['observations','full'],questions_per_mode=60)
    if not args.execute:
        print(json.dumps(plan,indent=2))
        return 0
    if Path.cwd().resolve()!=ROOT or output.parent!=Path('/home/zhoujunye/mas/outputs'):
        raise ValueError('Run from the frozen source root into a fresh server outputs child')
    protocol=Path(str(output)+'.protocol.json'); status=Path(str(output)+'.driver-status.json')
    export=Path(str(output)+'-export.json'); report_path=Path(str(output)+'-report')
    if any(p.exists() for p in (output,protocol,status,export,report_path)):
        raise ValueError('Never resume or replace an existing attempt batch')
    os.umask(0o077)
    write_json(protocol,settings())
    command=['--root','/home/zhoujunye/mas-data','--output',str(output),'--proofs',str(args.proofs.resolve()),
        '--image','mas/research-benchmarks:20261103-v1','--backends','claude-code-subagents',
        '--evidence-modes','observations','full','--effort','high','--concurrency','6','--judge-concurrency','2',
        '--task-manifest',str(MANIFEST),'--protocol-settings',str(protocol),'--tasks-per-benchmark','20',
        '--authorized-attempts','120','--authorized-judges','106','--execute']
    if args.retain_started_from:
        command+=['--retain-started-from',str(args.retain_started_from.resolve())]
    matrix_status=report_status=None
    try:
        matrix_status=benchmark_matrix.main(command)
        report=timeout_zero(collect(output)); report['condition_label']='Observation vs Full'
        write_report(report,report_path); write_json(export,report); report_status=0
    finally:
        write_json(status,dict(matrix_exit_code=matrix_status,report_exit_code=report_status,finished_at=now()))
    return 0 if matrix_status==0 and report_status==0 else 1


if __name__=='__main__':
    raise SystemExit(main())
