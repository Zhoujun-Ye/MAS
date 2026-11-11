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
import threading
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlsplit

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from common.io import write_json
from scripts.common import run
from scripts.probes.native_transport import frames
from scripts.probes.offline_gateway import Response, sse
from harness.runtime_support import credential_gateway


class WorkflowFixture:
    def __init__(self, backend, command, answer='2', pdf=False):
        self.single = backend == 'claude-code-single-agent'
        self.command, self.answer = command, answer
        self.pdf=pdf
        self.requests, self.errors = [], []
        self.lock = threading.Lock()

    def respond(self, request):
        body = json.loads(request.data)
        if urlsplit(request.full_url).path.endswith('count_tokens'):
            return Response(b'{"input_tokens":100}', 'application/json')
        with self.lock:
            if len(self.requests) >= 32:
                raise ValueError('Synthetic request ceiling exceeded')
            self.requests.append(body)
            block = self.next(body)
            response = dict(id='workflow-'+str(len(self.requests)), type='message', role='assistant',
                model=body['model'], content=[block], stop_reason='tool_use' if block['type']=='tool_use' else 'end_turn',
                stop_sequence=None, usage=dict(input_tokens=100, output_tokens=10,
                    cache_creation_input_tokens=0, cache_read_input_tokens=0))
        return sse(frames(response)) if body.get('stream') else Response(json.dumps(response).encode(), 'application/json')

    def next(self,body):
        messages = body.get('messages', [])
        user = next((m.get('content', []) for m in messages if m.get('role')=='user'), [])
        text = user if isinstance(user,str) else ' '.join(b.get('text','') for b in user if isinstance(b,dict))
        worker = not self.single and 'OFFLINE_WORKER_INPUT_PROBE' in text
        role = 'worker' if worker else 'lead'
        results = {b['tool_use_id']: b for m in messages for b in
            (m.get('content',[]) if isinstance(m.get('content'),list) else [])
            if isinstance(b,dict) and b.get('type')=='tool_result'}
        def tool(step,name,args):return dict(type='tool_use',id='workflow-'+role+'-'+step,name=name,input=args)
        def done(step):return 'workflow-'+role+'-'+step in results
        errors=[b for b in results.values() if b.get('is_error')]
        if errors:
            self.errors.extend(errors)
            return dict(type='text',text='Offline workflow failed; do not retry.')
        if not done('read'):return tool('read','Bash',dict(command=self.command,description='Verify mounted inputs'))
        if self.pdf and not done('pdf'):
            return tool('pdf','Read',dict(file_path='/workspace/pdf-probe.pdf',pages='1'))
        if worker:return dict(type='text',text='Offline worker input check complete.')
        if not self.single and not done('delegate'):
            return tool('delegate','Agent',dict(description='Offline native worker',subagent_type='general-purpose',
                prompt='OFFLINE_WORKER_INPUT_PROBE: inspect mounted inputs with the supplied tools. Return findings only.'))
        if not done('submit'):return tool('submit','Write',dict(file_path='/workspace/submission.json',
            content=json.dumps({'final_answer':self.answer})))
        return dict(type='text',text='Offline workflow complete.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--image',default=run.runtime.DEFAULT_SOLVER_IMAGE)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--effort',choices=run.runtime.EFFORTS,default=run.runtime.DEFAULT_EFFORT)
    args=parser.parse_args()
    if not args.execute:print(json.dumps(dict(status='planned',paid_calls=0,conditions=6)));return
    args.output.mkdir(parents=True,exist_ok=False)
    image=json.loads(subprocess.check_output(['docker','image','inspect',args.image],text=True))[0]['Id']
    dc=next(t for t in run.dataclaw_tasks(args.root/'dataclawbench/upstream') if not t.web)
    hdr=next(t for t in run.hybrid_tasks(args.root/'hybriddeepresearch/release/hybrid_ds_release/hybrid_ds_release.jsonl') if t.category=='search_to_sql')
    fda=next(t for t in run.fda.load_tasks(args.root/'fdabench/release') if run.fda.needs_corpus(t)
        and run.fda.database_path(t,args.root/'fdabench/data').is_file())
    jobs=[];fixtures={}
    for original in (dc,hdr,fda):
        for backend in run.BACKENDS:
            mode='single' if backend.endswith('single-agent') else 'structured'
            reference={k:original.reference[k] for k in ('database_type','tools_available')} if original.benchmark=='fdabench' else {}
            answer='["A"]' if original.benchmark=='fdabench' else '2'
            task=replace(original,question='Offline input access test. Submit the synthetic fixture answer.',reference=reference,web=False)
            data=args.root/('dataclawbench/upstream/assets/database' if task.benchmark=='dataclawbench' else task.benchmark+'/data')
            code=('from pathlib import Path; p=next(p for p in Path("/data").rglob("*") if p.is_file()); p.open("rb").read(80); '
                  'print(\'{"final_answer":"2"}\')')
            if task.benchmark=='hybriddeepresearch':
                code=f'import sqlite3; c=sqlite3.connect("file:/data/{task.db}/{task.db}_template.sqlite?mode=ro",uri=True); c.execute("SELECT name FROM sqlite_master LIMIT 1").fetchall(); c.close(); print(\'{{"final_answer":"2"}}\')'
            command='python3 -c '+shlex.quote(code)
            if task.benchmark=='hybriddeepresearch':
                command=('python3 /benchmark-tools.py sql --db '+shlex.quote(f'/data/{task.db}/{task.db}_template.sqlite')+
                         ' --query '+shlex.quote('SELECT name FROM sqlite_master LIMIT 1')+' >/dev/null && '+command)
            if task.benchmark=='fdabench':
                command=('python3 /benchmark-tools.py sql --db /data/database.sqlite --query '+
                    shlex.quote('SELECT name FROM sqlite_master LIMIT 1')+' >/dev/null && '+
                    'python3 /document-tools.py --query data --limit 1 >/dev/null && python3 -c '+
                    shlex.quote("from pypdf import PdfWriter; w=PdfWriter(); w.add_blank_page(width=300,height=300); w.write('/workspace/pdf-probe.pdf')"))
            thread_check=("import os,numpy; from threadpoolctl import threadpool_info; "
                f"assert all(os.environ.get(k)=={str(run.runtime.DEFAULT_COMPUTE_THREADS)!r} for k in {list(run.runtime.THREADS)!r}); "
                f"assert all(p['num_threads']<={run.runtime.DEFAULT_COMPUTE_THREADS} for p in threadpool_info())")
            command='python3 -c '+shlex.quote(thread_check)+' && '+command
            fixture=WorkflowFixture(backend,command,answer,pdf=task.benchmark=='fdabench');key='synthetic-'+secrets.token_hex(24);fixtures[key]=fixture
            options=SimpleNamespace(output=args.output/task.benchmark/mode,backend=backend,
                upstream=args.root/(task.benchmark+'/upstream'),data=data,data_variant='database',
                image=image,web_search='deepseek',max_web_requests=4,
                effort=args.effort,cpus=run.runtime.DEFAULT_CPUS,compute_threads=run.runtime.DEFAULT_COMPUTE_THREADS,record_resources=True,timeout=180,max_budget_usd=None,
                asset_cache=args.output/'asset-digests.sqlite')
            jobs.append((task,options,key,fixture,mode))
    def fake(request):
        key=request.get_header('Authorization','').removeprefix('Bearer ')
        if key not in fixtures or not request.full_url.startswith('https://api.deepseek.com/anthropic/'):
            raise RuntimeError('Non-synthetic upstream request blocked')
        return fixtures[key].respond(request)
    def execute(job):
        task,options,key,fixture,mode=job
        result=run.attempt(task,options,key)
        passed=(result['status']=='cli_exited' and result.get('final_answer')==fixture.answer
                and result.get('native_audit',{}).get('passed') and not fixture.errors)
        return dict(benchmark=task.benchmark,condition=mode,passed=bool(passed),status=result['status'],
            fake_requests=len(fixture.requests),resources=result.get('resources'),
            native_audit_passed=result.get('native_audit',{}).get('passed'))
    with patch.object(credential_gateway,'open_upstream',fake):
        with ThreadPoolExecutor(4) as pool:results=list(pool.map(execute,jobs))
    proof=dict(passed=all(r['passed'] for r in results),paid_calls=0,network='none',real_credentials=False,results=results)
    write_json(args.output/'summary.json',proof);print(json.dumps(proof))
    if not proof['passed']:raise SystemExit(1)


if __name__=='__main__':main()
