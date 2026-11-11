"""Offline numerical-thread benchmark; no agents, credentials, task data or network."""

import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from common.io import write_json
from harness.runtime_support.runtime import container, stop_container, DEFAULT_SOLVER_IMAGE
from harness.runtime_support.resources import ContainerResources


COMPUTE = '''import json,time,numpy as np
from threadpoolctl import threadpool_info
rng=np.random.default_rng(20261106)
a=rng.standard_normal((2304,2304)); b=rng.standard_normal((2304,2304))
a@b
elapsed=[];cpu=[]
for _ in range(5):
 t=time.perf_counter();c=time.process_time();out=a@b
 elapsed.append(time.perf_counter()-t);cpu.append(time.process_time()-c)
print(json.dumps(dict(seconds=elapsed,cpu_seconds=cpu,checksum=float(out[0,0]),
 blas=[dict(internal_api=x['internal_api'],num_threads=x['num_threads']) for x in threadpool_info()])))
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--image',default=DEFAULT_SOLVER_IMAGE)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    if not args.execute:
        print(json.dumps(dict(status='planned',paid_calls=0,cpus=8,threads=[1,2,4,8],
                              serial_for_measurement=True)))
        return
    args.output.mkdir(parents=True,exist_ok=False)
    image=json.loads(subprocess.check_output(['docker','image','inspect',args.image],text=True))[0]['Id']
    results=[]
    for threads in (1,2,4,8):
        root=args.output/str(threads); work=root/'workspace';profile=root/'native-profile'
        work.mkdir(parents=True);(profile/'home').mkdir(parents=True)
        identity=container(work,profile,work,image,network='none',cpus=8,compute_threads=threads)
        monitor=None
        try:
            monitor=ContainerResources(identity,root,8,interval=.25).start()
            raw=subprocess.check_output(['docker','exec',identity,'python3','-c',COMPUTE],text=True,timeout=180)
            observed=json.loads(raw)
            assert observed['blas'] and all(x['num_threads']==threads for x in observed['blas'])
            results.append(dict(threads=threads,**observed))
        finally:
            try:
                if monitor is not None: monitor.close()
            finally:
                try: stop_container(identity)
                finally: subprocess.run(['docker','rm','-f',identity],check=True,capture_output=True)
    result=dict(image_id=image,results=results,paid_calls=0,network='none',serial_for_measurement=True,
                scope='Synthetic BLAS capability only; not benchmark task or end-to-end model speedup')
    write_json(args.output/'summary.json',result)
    print(json.dumps(result))


if __name__=='__main__':
    main()
