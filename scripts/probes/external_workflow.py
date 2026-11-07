"""Real external-runner/native-CLI smoke with synthetic provider and real input mounts."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
import secrets
import shlex
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from common.io import write_json
from scripts.common import run
from scripts.probes.evidence_mas import Fixture,decoded
from harness.runtime_support import credential_gateway


class WorkflowFixture(Fixture):
    def __init__(self,full,command):
        super().__init__('full' if full else 'structured')
        self.full,self.command=full,command

    def next(self,body):
        step=len(self.requests)-1
        def tool(name,args):return dict(type='tool_use',id='external-'+str(step),name=name,input=args)
        errors=[x for m in body.get('messages',[]) for x in m.get('content',[]) if isinstance(x,dict) and x.get('is_error')]
        if errors:
            self.errors.extend(errors)
            return dict(type='text',text='Offline workflow failed; do not retry.')
        if step in (0,2):return tool('Bash',dict(command=self.command,description='Read mounted inputs and emit synthetic declared answer'))
        if step==1:return tool('Agent',dict(description='Offline native worker',subagent_type='evidence-worker' if self.full else 'general-purpose',prompt='Read the mounted inputs with the supplied synthetic probe. Return findings only.'))
        if step==3:return dict(type='text',text='Offline worker complete.')
        if self.full and step==4:return tool('mcp__evidence__decision_view',{})
        if self.full and step==5:
            view=next(d for d in decoded(body) if d.get('candidates'))
            return tool('mcp__evidence__decision_read',dict(candidate_id=view['candidates'][0]['id'],source_cursor=1))
        if step==(6 if self.full else 4):return tool('Write',dict(file_path='/workspace/submission.json',content='{"final_answer":"2"}'))
        return dict(type='text',text='Offline workflow complete.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--image',default='mas/research-benchmarks:20261103-v1')
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    if not args.execute:print(json.dumps(dict(status='planned',paid_calls=0,conditions=4)));return
    args.output.mkdir(parents=True,exist_ok=False)
    image=json.loads(subprocess.check_output(['docker','image','inspect',args.image],text=True))[0]['Id']
    dc=next(t for t in run.dataclaw_tasks(args.root/'dataclawbench/upstream') if not t.web)
    hdr=next(t for t in run.hybrid_tasks(args.root/'hybriddeepresearch/release/hybrid_ds_release/hybrid_ds_release.jsonl') if t.category=='search_to_sql')
    jobs=[];fixtures={}
    for original in (dc,hdr):
        for full in (False,True):
            mode='full' if full else 'structured';task=replace(original,question='Offline input access test. Return exactly the string 2.',reference={},web=False)
            data=args.root/('dataclawbench/upstream/assets/database' if task.benchmark=='dataclawbench' else 'hybriddeepresearch/data')
            code=('from pathlib import Path; p=next(p for p in Path("/data").rglob("*") if p.is_file()); p.open("rb").read(80); '
                  'print(\'{"final_answer":"2"}\')')
            if task.db:
                code=f'import sqlite3; c=sqlite3.connect("file:/data/{task.db}/{task.db}_template.sqlite?mode=ro",uri=True); c.execute("SELECT name FROM sqlite_master LIMIT 1").fetchall(); c.close(); print(\'{{"final_answer":"2"}}\')'
            command='python3 -c '+shlex.quote(code)
            if task.db:
                command=('python3 /benchmark-tools.py sql --db '+shlex.quote(f'/data/{task.db}/{task.db}_template.sqlite')+
                         ' --query '+shlex.quote('SELECT name FROM sqlite_master LIMIT 1')+' >/dev/null && '+command)
            fixture=WorkflowFixture(full,command);key='synthetic-'+secrets.token_hex(24);fixtures[key]=fixture
            options=SimpleNamespace(output=args.output/task.benchmark/mode,backend='claude-code-subagents',
                upstream=args.root/(task.benchmark+'/upstream'),data=data,data_variant='database',
                image=image,web_search='deepseek',max_web_requests=4,evidence_mode='full' if full else None,
                effort='high',cpus=8,compute_threads=4,record_resources=True,timeout=180,max_budget_usd=None)
            jobs.append((task,options,key,fixture,mode))
    def fake(request):
        key=request.get_header('Authorization','').removeprefix('Bearer ')
        if key not in fixtures or not request.full_url.startswith('https://api.deepseek.com/anthropic/'):
            raise RuntimeError('Non-synthetic upstream request blocked')
        return fixtures[key].respond(request)
    def execute(job):
        task,options,key,fixture,mode=job
        result=run.attempt(task,options,key)
        passed=(result['status']=='cli_exited' and result.get('final_answer')=='2'
                and result.get('native_audit',{}).get('passed') and not fixture.errors)
        if mode=='full':passed=passed and result.get('decision_gate',{}).get('accepted') is True
        return dict(benchmark=task.benchmark,condition=mode,passed=bool(passed),status=result['status'],
            fake_requests=len(fixture.requests),resources=result.get('resources'),
            decision_gate=result.get('decision_gate'),native_audit_passed=result.get('native_audit',{}).get('passed'))
    with patch.object(credential_gateway,'open_upstream',fake):
        with ThreadPoolExecutor(4) as pool:results=list(pool.map(execute,jobs))
    proof=dict(passed=all(r['passed'] for r in results),paid_calls=0,network='none',real_credentials=False,results=results)
    write_json(args.output/'summary.json',proof);print(json.dumps(proof))
    if not proof['passed']:raise SystemExit(1)


if __name__=='__main__':main()
