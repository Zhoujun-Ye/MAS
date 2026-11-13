"""Real pinned-CLI E4 resume/role proof with synthetic provider responses only."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import secrets
import shlex
from unittest.mock import patch

from benchmarks.kramabench.tasks import load_tasks
from common.io import fingerprint, read_json, write_json
from harness.runtime_support import credential_gateway, runtime as shared
from harness.runtime_support.inference import proof_requests
from scripts.probes.offline_gateway import Fixture
from .e4_runtime import VARIANTS, edited_brief, WORKER_REPORT
from .e4_trial import attempt
from .free_probe import tool

REPORT_MARKER='E4_SYNTHETIC_PAIRED_REPORT_NO_FUTURE_STATE'


class ReplayFixture(Fixture):
    def __init__(self,phase):
        super().__init__('claude-code-single-agent' if phase=='worker' else 'claude-code-subagents',
                         delegation_check='e4-free-replay')
        self.phase=phase

    def delegation_block(self,body):
        blocks=[b for m in body.get('messages',[]) for b in m.get('content',[]) if isinstance(b,dict)]
        done={b.get('tool_use_id') for b in blocks if b.get('type')=='tool_result'}
        if self.phase=='worker':
            if 'inspect-input' not in done:
                return tool('inspect-input','Bash',command='ls /data | head -3',description='Inspect supplied input')
            return dict(type='text',text=json.dumps(dict(observations=REPORT_MARKER,checks=[],candidate_answer=2)))
        if 'save-answer' not in done:
            code=("from pathlib import Path; import json; "
                "assert not Path('future-secret.txt').exists(); "
                "Path('pipeline.py').write_text('import json\\nprint(json.dumps({\"answer\":2}))\\n'); "
                "Path('submission.json').write_text(json.dumps(dict(answer=2,pipeline_path='pipeline.py',evidence='synthetic',unfinished=[])))")
            return tool('save-answer','Bash',command='python3 -c '+shlex.quote(code),description='Write synthetic answer')
        return dict(type='text',text='Synthetic E4 lead complete.')


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--root',type=Path,default=Path('/home/zhoujunye/mas-data'))
    p.add_argument('--image',default=shared.DEFAULT_SOLVER_IMAGE)
    p.add_argument('--execute',action='store_true');args=p.parse_args(argv)
    if not args.execute:print(dict(paid_calls=0,status='planned'));return 0
    args.output.mkdir(parents=True,exist_ok=False)
    manifest=read_json(args.manifest);cases=manifest['cases']
    upstream=args.root/'kramabench/upstream';tasks={t.id:t for t in load_tasks(upstream)[0]}
    image=json.loads(__import__('subprocess').check_output(['docker','image','inspect',args.image]))[0]['Id']
    source=shared.source_manifest()
    # Both built-in worker roles are probed; every frozen lead prefix is resumed natively.
    jobs=[('worker',v,next(c for c in cases if c['prefix']['agent_type']==role))
          for role in sorted({c['prefix']['agent_type'] for c in cases}) for v in VARIANTS]
    jobs += [('lead','verbatim',c) for c in cases]
    fixtures={'synthetic-'+secrets.token_hex(24):(phase,v,c,ReplayFixture(phase)) for phase,v,c in jobs}
    def fake(request):
        key=request.get_header('Authorization','').removeprefix('Bearer ')
        if key not in fixtures or not request.full_url.startswith('https://api.deepseek.com/anthropic/'):
            raise ValueError('E4 proof forbids real dispatch')
        return fixtures[key][3].respond(request)
    def probe(item):
        key,(phase,variant,case,fixture)=item
        name=f"{phase}-{case['task_id']}-{variant}"
        output=args.output/name
        result=attempt(tasks[case['task_id']],case,phase,variant,output,upstream,image,key,
                       report_text=REPORT_MARKER if phase=='lead' else None,timeout=90)
        first=fixture.requests[0] if fixture.requests else {}
        messages=first.get('messages',[])
        config=proof_requests(fixture.requests,'none')
        check=dict(phase=phase,variant=variant,task_id=case['task_id'],status=result['status'],
                   native_status=result.get('cli',{}).get('status'),**config)
        if phase=='worker':
            exact=edited_brief(case,variant)+'\n'+WORKER_REPORT
            check['prompt_exact']=any(b.get('text','').strip()==exact.strip()
                for m in messages for b in m.get('content',[]) if isinstance(b,dict))
            names={t['name'] for t in first.get('tools',[])}
            check['role_surface_verified']=('Agent' not in names and 'Bash' in names
                and (('Write' not in names and 'Edit' not in names) if case['prefix']['agent_type']=='Explore'
                     else ('Write' in names and 'Edit' in names)))
            check['input_inspected']='inspect-input' in json.dumps(fixture.requests[-1]) if fixture.requests else False
            check['report_returned']=REPORT_MARKER in result.get('e4_worker_receipt',{}).get('text','')
            passed=all(check.get(k) is True for k in ('prompt_exact','input_inspected','report_returned','role_surface_verified'))
        else:
            blocks=[b for m in messages for b in m.get('content',[]) if isinstance(b,dict)]
            saved=case['prefix'];uses=[b for b in blocks if b.get('type')=='tool_use' and b.get('id')==saved['call_id']]
            responses=[b for b in blocks if b.get('type')=='tool_result' and b.get('tool_use_id')==saved['call_id']]
            check['recorded_call_exact']=len(uses)==1 and uses[0]['input']['prompt']==saved['brief']
            check['paired_report_exact']=len(responses)==1 and responses[0].get('content')==REPORT_MARKER
            # Native may coalesce adjacent text, but must preserve every substantive historical text block.
            originals=[b['text'] for r in saved['rows'] for b in (r.get('message') or {}).get('content',[])
                       if isinstance(b,dict) and b.get('type')=='text']
            check['prefix_text_preserved']=all(t in json.dumps(messages,ensure_ascii=False) or
                any(t in b.get('text','') for b in blocks) for t in originals)
            check['fresh_workspace_submission']=(output/case['task_id']/'claude-code-subagents/workspace/submission.json').is_file()
            passed=all(check.get(k) is True for k in ('recorded_call_exact','paired_report_exact','prefix_text_preserved','fresh_workspace_submission'))
        check['passed']=passed and config['request_configuration_verified'] and result.get('cli',{}).get('status')=='cli_exited'
        write_json(output/'fake-provider-requests.json',fixture.requests)
        write_json(output/'proof.json',check)
        return name,check
    with patch.object(credential_gateway,'open_upstream',fake):
        with ThreadPoolExecutor(max_workers=3) as pool:checks=dict(pool.map(probe,fixtures.items()))
    proof=dict(passed=all(c['passed'] for c in checks.values()),paid_calls=0,real_credentials=False,
        source_manifest=source,manifest_sha256=fingerprint(manifest),checks=checks,
        runtime_binding=dict(image_id=image,binary_sha256=hashlib.sha256(shared.CLAUDE.read_bytes()).hexdigest()))
    assert source==shared.source_manifest()
    write_json(args.output/'proof.json',proof)
    print(json.dumps(dict(passed=proof['passed'],checks=checks,paid_calls=0)))
    return 0 if proof['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
