"""Bounded offline OOM telemetry check: no provider, credentials or task inputs."""

import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from harness.runtime_support.runtime import container,stop_container
from harness.runtime_support.resources import ContainerResources
from common.io import write_json


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--image',default='mas/research-benchmarks:20261103-v1')
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    if not args.execute:
        print(json.dumps(dict(status='planned',paid_calls=0,memory_limit_mib=64)))
        return
    args.output.mkdir(parents=True,exist_ok=False)
    work=args.output/'workspace';profile=args.output/'native-profile'
    work.mkdir();(profile/'home').mkdir(parents=True)
    identity=container(work,profile,work,args.image,network='none',cpus=1)
    collector=None
    try:
        subprocess.run(['docker','update','--memory','64m','--memory-swap','64m',identity],check=True,capture_output=True,timeout=15)
        collector=ContainerResources(identity,args.output,1,interval=.1).start()
        result=subprocess.run(['docker','exec',identity,'python3','-c','x=bytearray(128*1024*1024); print(len(x))'],capture_output=True,text=True,timeout=30)
        observed=collector.close()
        assert result.returncode!=0 and observed['memory']['oom_observed'],observed
    finally:
        try:
            if collector is not None:collector.close()
        finally:
            try:
                stop_container(identity)
                if collector is not None:collector.record_exit()
            finally:
                subprocess.run(['docker','rm','-f',identity],check=True,capture_output=True,timeout=15)
    proof=dict(passed=True,paid_calls=0,network='none',memory_limit_mib=64,
               allocation_mib=128,exec_returncode=result.returncode,resources=collector.result,
               container_removed=True)
    write_json(args.output/'proof.json',proof)
    print(json.dumps(proof))


if __name__=='__main__':
    main()
