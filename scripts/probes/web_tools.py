"""Real-image web helpers through a fake-provider host gateway; no real keys."""

import argparse
from contextlib import nullcontext
import io
import json
from pathlib import Path
import subprocess
import sys
import urllib.error
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from common.io import write_json
from harness.runtime_support import runtime,credential_gateway as cg,web_fetch


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--image',default='mas/research-benchmarks:20261103-v1')
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--public-fetch',action='store_true',help='One non-paid Wikipedia GET via the local tunnel')
    args=parser.parse_args()
    if not args.execute:print('{"paid_calls":0,"status":"planned"}');return
    args.output.mkdir(parents=True,exist_ok=False)
    work,profile=args.output/'workspace',args.output/'native-profile'
    work.mkdir();(profile/'home').mkdir(parents=True)
    calls=[]
    class Response(io.BytesIO):
        status=200
        headers={}
    def provider(request):
        assert request.full_url=='https://api.deepseek.com/v1/tools/search'
        body=json.loads(request.data);assert body['count']==10
        calls.append(body['query'])
        if body['query']=='synthetic-failure':
            raise urllib.error.HTTPError(request.full_url,404,'fixture',{},io.BytesIO(b'{}'))
        return Response(json.dumps(dict(results=[dict(title=f'Fixture {i}',url=f'https://example.org/{i}',
            summary='s'*1800,content='COMPLETE_BODY_'+str(i)+'x'*10000) for i in range(10)])).encode())
    url='https://en.wikipedia.org/wiki/SQLite' if args.public_fetch else 'https://example.org/public'
    api=('https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch=SQLite&format=json&srlimit=3'
         if args.public_fetch else 'https://example.org/api.json')
    # The last call runs outside /workspace: shared artifacts must still land there.
    commands=[('/workspace',['search','--query','synthetic-search']),('/workspace',['fetch','--url',url]),
              ('/workspace',['fetch','--url',api]),('/workspace',['search','--query','synthetic-failure']),
              ('/workspace',['search','--query','synthetic-after-failure']),
              ('/tmp',['search','--query','synthetic-outside-workspace'])]
    results=[]
    identity=None
    fetch_patch=nullcontext() if args.public_fetch else patch.object(web_fetch,'fetch',lambda url,**kw:dict(url=url,title='Fixture',content='public fixture'))
    with patch.object(cg,'open_upstream',provider),fetch_patch:
        with cg.CredentialGateway('synthetic-host-key',web_limit=20,
                unix_path=profile/'gateway.sock',ledger_path=args.output/'gateway-requests.jsonl') as gateway:
            try:
                identity=runtime.container(work,profile,work,args.image,gateway=gateway,
                    dataset_mounts=[(Path(__file__).resolve().parents[2]/'harness/runtime_support/tools.py','/benchmark-tools.py',True)],
                    environment_overrides=dict(MAS_BENCHMARK_WEB='1',MAS_WEB_PROVIDER='deepseek',MAS_WEB_MAX_REQUESTS='20'))
                for cwd,command in commands:
                    # Longer than the helper's own client timeout, so the helper reports it.
                    result=subprocess.run(['docker','exec','--workdir',cwd,identity,'python3','/benchmark-tools.py',*command],
                                          capture_output=True,text=True,timeout=60)
                    assert 'synthetic-host-key' not in result.stdout+result.stderr
                    expected=command[-1]=='synthetic-failure'
                    assert (result.returncode!=0)==expected,(command,result.returncode,result.stderr)
                    if not expected:
                        first=json.loads(result.stdout.splitlines()[0])
                        assert first['web_budget']['remaining'] in range(15,20)
                        assert first['full_result_file'].startswith('/workspace/web/')
                        if command[0]=='search':assert len(result.stdout.splitlines())==11
                        if args.public_fetch and command[-1]==api:assert '"query"' in result.stdout
                        assert len(result.stdout.encode())<24000
                    results.append(dict(action=command[0],cwd=cwd,failed_fixture=expected,returncode=result.returncode))
            finally:
                if identity:
                    runtime.stop_container(identity)
                    subprocess.run(['docker','rm','-f',identity],check=True,capture_output=True,timeout=15)
        assert gateway.summary()['web_reservations']==5
    assert len(calls)==4
    files=list((work/'web').glob('search-*.json'))
    assert len(files)==3 and all(len(json.loads(p.read_text())['results'])==10 for p in files)
    assert len(list((work/'web').glob('fetch-*.json')))==2
    proof=dict(passed=True,paid_calls=0,real_credentials=False,network='none',
               public_fetch_via_local_tunnel=args.public_fetch,
               results=results,gateway=gateway.summary(),full_search_artifacts=len(files))
    write_json(args.output/'summary.json',proof);print(json.dumps(proof))


if __name__=='__main__':main()
