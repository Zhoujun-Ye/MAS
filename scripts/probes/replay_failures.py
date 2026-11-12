"""Free Docker replay-origin checks; synthetic artifacts, no model or judge calls."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from common.io import write_json
from scripts.kramabench import cli_runtime as krama


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--image',default=krama.runtime.DEFAULT_SOLVER_IMAGE)
    p.add_argument('--execute',action='store_true')
    args=p.parse_args(argv)
    if not args.execute:
        print(json.dumps(dict(status='planned',cases=6,paid_calls=0)))
        return 0
    args.output.mkdir(parents=True,exist_ok=False)
    upstream=args.output/'upstream';(upstream/'data').mkdir(parents=True)
    cases=[('missing-image',0,'harness_error'),('missing-mount',0,'harness_error'),
           *[(f'process-{c}',c,'runtime_error') for c in (1,125,126,127)]]
    results=[]
    for name,code,expected in cases:
        folder=args.output/name;work=folder/'workspace';work.mkdir(parents=True)
        (work/'pipeline.py').write_text(f'import sys\nsys.exit({code})\n')
        write_json(work/'submission.json',dict(answer=1,pipeline_path='pipeline.py',evidence='synthetic',unfinished=[]))
        options=SimpleNamespace(upstream=upstream if name!='missing-mount' else args.output/'absent-upstream',
            image=args.image if name!='missing-image' else 'mas-nonexistent-replay-check:never-pull',
            cpus=8,compute_threads=4,replay_timeout=30)
        with patch.object(krama,'grade_answer',return_value=dict(status='graded',score=1,judge_calls=0)):
            report=krama.collect_attempt(folder,dict(task_id='synthetic',backend='claude-code-subagents',status='cli_exited'),options)
        name_owned=json.loads((folder/'replay/container-ownership.json').read_text())['container_name']
        remaining=subprocess.run(['docker','ps','-aq','--filter','name=^/'+name_owned+'$'],
                                 capture_output=True,text=True,timeout=15)
        removed=remaining.returncode==0 and not remaining.stdout.strip()
        result=dict(case=name,status=report['pipeline_replay']['status'],exit_code=report.get('pipeline_exit_code'),
                    raw_grade_unchanged=report['grade']['score']==1,
                    container_removed=removed,
                    passed=report['pipeline_replay']['status']==expected and report['grade']['score']==1 and removed)
        results.append(result)
    summary=dict(passed=all(r['passed'] for r in results),paid_calls=0,real_credentials=False,
                 network='none',results=results)
    write_json(args.output/'verification.json',summary);print(json.dumps(summary))
    return 0 if summary['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
