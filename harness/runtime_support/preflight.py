"""No-model container admission shared by benchmark workflows."""

import subprocess
from common.io import write_json
from .runtime import CLAUDE,container,stop_container,capability_command
from .resources import ContainerResources


def check(work,profile,image,mounts,backend,effort,cpus,threads,output,data_command,modules=(),probes=(),record_resources=False):
    identity=container(work,profile,work,image,network='none',backend=backend,
                       dataset_mounts=mounts,effort=effort,cpus=cpus,compute_threads=threads)
    collector=None
    try:
        if record_resources:collector=ContainerResources(identity,output,cpus).start()
        commands=[[str(CLAUDE),'--version'],capability_command(modules),data_command,[str(CLAUDE),'--help']]
        commands.extend(['python3','-c',p['source']] for p in probes)
        rows=[]
        for command in commands:
            try:
                r=subprocess.run(['docker','exec',identity,*command],capture_output=True,text=True,timeout=60)
                rows.append(dict(argv=command,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr))
                write_json(output/'checks.json',rows);r.check_returncode()
            except subprocess.TimeoutExpired:
                rows.append(dict(argv=command,status='timeout',timeout_seconds=60))
                write_json(output/'checks.json',rows)
                raise
        return dict(paid_calls=0,network='none',checks=len(rows))
    finally:
        try:
            if collector:collector.close()
        finally:
            try:
                stop_container(identity)
                if collector:collector.record_exit()
            finally:subprocess.run(['docker','rm','-f',identity],check=True,capture_output=True,timeout=15)
