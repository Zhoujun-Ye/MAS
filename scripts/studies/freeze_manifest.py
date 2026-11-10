"""Freeze full public task IDs/fingerprints in upstream order; no model calls."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from scripts.studies.benchmark_matrix import SUPPORTED_BENCHMARKS,task_pools,task_fingerprint
from common.io import write_json


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--benchmarks',nargs='+',choices=SUPPORTED_BENCHMARKS,required=True)
    parser.add_argument('--protocol-settings',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    if args.output.exists() or len(set(args.benchmarks))!=len(args.benchmarks):
        raise ValueError('Use a fresh output and unique benchmarks')
    pools=task_pools(args.root,args.benchmarks)
    manifest=dict(kind='benchmark-full-v1',order_policy='upstream-order-unchanged',
        baseline_settings=json.loads(args.protocol_settings.read_text()),
        benchmarks={b:[dict(task_id=t.id,task_sha256=task_fingerprint(b,t)) for t in tasks]
                    for b,tasks in pools.items()})
    for rows in manifest['benchmarks'].values():
        if not rows or len({r['task_id'] for r in rows})!=len(rows):
            raise ValueError('Empty task pool or duplicate IDs')
    write_json(args.output,manifest)
    print(json.dumps(dict(paid_calls=0,counts={b:len(v) for b,v in manifest['benchmarks'].items()},
                         order_policy=manifest['order_policy'])))


if __name__=='__main__':
    main()
