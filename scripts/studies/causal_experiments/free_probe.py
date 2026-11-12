"""Exercise all six study roles with the pinned native CLI and a fake provider."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
import json
import re
from pathlib import Path
import secrets
import shlex
import subprocess
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from benchmarks.kramabench.tasks import load_tasks
from common.io import write_json
from harness.runtime_support import credential_gateway, runtime as shared
from harness.runtime_support.inference import proof_requests
from harness.runtime_support.proof import validate_surface
from scripts.kramabench import cli_runtime as krama
from scripts.probes.offline_gateway import Fixture
from .runtime import ROLES, backend_for, solver_packet
from .hooks import NULL_REPORT,NULL_REQUEST
from .trial import attempt

CANARY='NATIVE_TASK_CANARY_NO_WORKER_ACCESS'


def tool(identity,name,**inputs):
    return dict(type='tool_use',id=identity,name=name,input=inputs)


class StudyFixture(Fixture):
    def __init__(self,arm,source):
        super().__init__(backend_for(arm),delegation_check='causal-free-check')
        self.arm,self.source=arm,source
        self.null_requests=[]

    def delegation_block(self,body):
        blocks=[b for m in body.get('messages',[]) for b in m.get('content',[]) if isinstance(b,dict)]
        done={b.get('tool_use_id') for b in blocks if b.get('type')=='tool_result'}
        if self.arm=='null_worker' and any(NULL_REQUEST in b.get('text','') for b in blocks):
            self.null_requests.append(body)
            if 'null-forbidden' not in done:
                return tool('null-forbidden','Bash',command='touch /workspace/forbidden-worker.txt',description='Must be denied')
            return dict(type='text',text=NULL_REPORT)
        worker=any(b.get('text')=='CAUSAL_REAL_WORKER' for b in blocks)
        if worker:
            if 'worker-read' not in done:
                return tool('worker-read','Bash',command='printf worker-ok',description='Offline worker check')
            return dict(type='text',text='Worker observations complete.')
        if self.arm=='recon':
            if 'recon-read' not in done:
                return tool('recon-read','Bash',command='test -r '+shlex.quote(self.source)+' && printf data-ok',description='Verify supplied input')
            if 'recon-save' not in done:
                packet=dict(task_qualifiers=['PROBE_RECON_INFO'],candidate_sources=[dict(path='/data',columns=[],units='unknown',relevance='synthetic source')],uncertainties=[])
                return tool('recon-save','Write',file_path='/workspace/recon.json',content=json.dumps(packet))
            if 'Fix /workspace/recon.json' in json.dumps(body) and 'recon-fix' not in done:
                packet=dict(task_qualifiers=['PROBE_RECON_INFO'],candidate_sources=[dict(path=self.source,columns=[],units='unknown',relevance='synthetic source')],uncertainties=[])
                return tool('recon-fix','Write',file_path='/workspace/recon.json',content=json.dumps(packet))
            return dict(type='text',text='Independent recon complete.')
        if self.arm in {'native','null_worker'} and 'delegate' not in done:
            if 'plan-task' not in done:
                return tool('plan-task','TaskCreate',subject=CANARY,description=CANARY,activeForm='Planning '+CANARY)
            return tool('delegate','Agent',description=CANARY,subagent_type='Explore' if self.arm=='null_worker' else 'general-purpose',prompt='CAUSAL_REAL_WORKER')
        if self.arm=='null_worker' and 'send-empty' not in done:
            target = re.search(r'agentId: (a[0-9a-f]+)', json.dumps(blocks))
            if target is None:
                raise ValueError('Native null-worker identity absent')
            return tool('send-empty','SendMessage',to=target[1],summary=CANARY,message=CANARY)
        if self.arm=='self_brief':
            if 'denied-before-brief' not in done:
                return tool('denied-before-brief','Bash',command='touch /workspace/forbidden.txt',description='Must be denied')
            if 'write-brief' not in done:
                return tool('write-brief','Write',file_path='/workspace/brief.md',
                    content='## Task\nCompute the requested statistic.\n## Qualifiers\nCheck dates and units.\n## Sources\nInspect the supplied input files.\n')
        if self.arm=='brief_prompt' and 'write-brief' not in done:
            return tool('write-brief','Write',file_path='/workspace/brief.md',
                content='## Task\nCompute.\n## Qualifiers\nCheck dates.\n## Sources\nInspect inputs.\n')
        if 'mount-check' not in done:
            code=("import pathlib,errno; paths=['/causal/hooks.py','/causal/policy.json','/causal/packet_validation.py']; "
                  "exec(\"for p in paths:\\n try: open(p,'a').close()\\n except OSError as e: assert e.errno in (errno.EROFS,errno.EACCES)\\n else: raise AssertionError('Study policy writable')\")")
            return tool('mount-check','Bash',command='python3 -c '+shlex.quote(code),description='Verify read-only study policy')
        if 'save-answer' not in done:
            code=("from pathlib import Path; import json; "
                  "Path('pipeline.py').write_text('import json\\nprint(json.dumps({\"answer\":2}))\\n'); "
                  "Path('submission.json').write_text(json.dumps(dict(answer=2,pipeline_path='pipeline.py',evidence='synthetic',unfinished=[])))")
            return tool('save-answer','Bash',command='python3 -c '+shlex.quote(code),description='Write synthetic solution')
        return dict(type='text',text='Offline causal role complete.')


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path('/home/zhoujunye/mas-data'))
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--image',default=shared.DEFAULT_SOLVER_IMAGE)
    p.add_argument('--execute',action='store_true')
    args=p.parse_args(argv)
    if not args.execute:
        print(json.dumps(dict(status='planned',roles=list(ROLES),paid_calls=0)));return 0
    args.output.mkdir(parents=True,exist_ok=False)
    image=json.loads(subprocess.check_output(['docker','image','inspect',args.image]))[0]['Id']
    upstream=args.root/'kramabench/upstream'
    task=replace(load_tasks(upstream)[0][0],query=load_tasks(upstream)[0][0].query+'\n'+CANARY)
    source='/data/'+str(next(p for p in (upstream/'data').rglob('*') if p.is_file()).relative_to(upstream/'data'))
    fixtures={'synthetic-'+secrets.token_hex(24):StudyFixture(arm,source) for arm in ROLES}
    source_manifest=shared.source_manifest()
    def fake(request):
        key=request.get_header('Authorization','').removeprefix('Bearer ')
        if key not in fixtures or not request.full_url.startswith('https://api.deepseek.com/anthropic/'):
            raise ValueError('Free study probe refused a non-synthetic dispatch')
        return fixtures[key].respond(request)
    def probe(item):
        key,fixture=item;arm=fixture.arm
        packet=solver_packet(dict(status='available',task_id=task.id,packet=dict(task_qualifiers=['PROBE_RECON_INFO'],candidate_sources=[],uncertainties=[]))) if arm=='recon_transplant' else None
        output=args.output/arm
        report=attempt(task,arm,output,upstream,image,key,packet=packet,timeout=90)
        folder=output/task.id/backend_for(arm)
        validate_surface(report['native_surface'],backend_for(arm))
        audit=report.get('single_agent_audit',report.get('subagents_audit',{}))
        check=dict(status=report['status'],native_audit_passed=audit.get('passed'),
            manipulation=report.get('manipulation_check'),**proof_requests(fixture.requests,'none'))
        passed=report['status']=='cli_exited' and audit.get('passed') is True and check['request_configuration_verified']
        if arm in {'single','native'}:
            from types import SimpleNamespace
            from scripts.common.prompts.conditions import condition_instructions
            from scripts.common.prompts.limits import limit_instructions
            options=SimpleNamespace(subagents_prompt='native' if arm=='native' else 'structured')
            expected=task.query+'\n\n'+krama.INSTRUCTIONS+limit_instructions(90)+'\n'+condition_instructions(options,backend_for(arm))
            check['baseline_prompt_exact']=(folder/'cli/prompt.txt').read_text()==expected
            passed=passed and check['baseline_prompt_exact']
        if arm=='recon':
            passed=passed and report['recon_receipt']['status']=='available'
            hooks=[json.loads(x) for x in (folder/'native-profile/observer/events.jsonl').read_text().splitlines()]
            check['stop_repair_observed']=any(r.get('causal_intervention',{}).get('action')=='recon_stop_blocked' for r in hooks)
            passed=passed and check['stop_repair_observed']
        else:
            from types import SimpleNamespace
            collected=krama.collect_attempt(folder,report,SimpleNamespace(upstream=upstream,image=image,cpus=8,compute_threads=4,replay_timeout=30))
            passed=passed and collected.get('pipeline_answer_matches_submission') is True and report['manipulation_check']['passed']
        if arm=='null_worker':
            check['null_worker_requests']=len(fixture.null_requests)
            check['worker_tools_denied']=bool(fixture.null_requests) and report['manipulation_check']['executed_worker_tools']==0 and 'null-forbidden' in fixture.rejections
            check['task_not_in_worker_context']=all(CANARY not in json.dumps(r) and 'CAUSAL_REAL_WORKER' not in json.dumps(r) for r in fixture.null_requests)
            passed=passed and check['worker_tools_denied'] and check['task_not_in_worker_context'] and not (folder/'workspace/forbidden-worker.txt').exists()
        if arm=='self_brief':passed=passed and not (folder/'workspace/forbidden.txt').exists() and 'denied-before-brief' in fixture.rejections
        if arm=='recon_transplant':
            check['task_id_absent']=task.id not in json.dumps(fixture.requests)
            passed=passed and 'PROBE_RECON_INFO' in json.dumps(fixture.requests) and check['task_id_absent']
        check['passed']=bool(passed)
        write_json(output/'free-role-proof.json',check)
        write_json(output/'fake-provider-requests.json',fixture.requests)
        return arm,check
    with patch.object(credential_gateway,'open_upstream',fake):
        with ThreadPoolExecutor(max_workers=3) as pool:
            roles=dict(pool.map(probe,fixtures.items()))
    by_arm={fixture.arm:fixture for fixture in fixtures.values()}
    first=lambda arm:{k:v for k,v in by_arm[arm].requests[0].items() if k!='metadata'}
    identical=first('native')==first('null_worker')
    roles['null_worker']['lead_initial_context_identical']=identical
    roles['null_worker']['passed']=roles['null_worker']['passed'] and identical
    brief_identical=first('self_brief')==first('brief_prompt')
    roles['brief_prompt']['instruction_context_identical']=brief_identical
    roles['brief_prompt']['passed']=roles['brief_prompt']['passed'] and brief_identical
    proof=dict(passed=all(r['passed'] for r in roles.values()),paid_calls=0,real_credentials=False,
        network='none',roles=roles,source_manifest=source_manifest,
        runtime_binding=dict(image_id=image,binary_sha256=hashlib.sha256(shared.CLAUDE.read_bytes()).hexdigest()),
        proof_kind='native_delegation_injection',scope='Study-only synthetic proof; cannot admit ordinary baseline launches')
    assert source_manifest==shared.source_manifest()
    write_json(args.output/'proof.json',proof)
    print(json.dumps({k:v for k,v in proof.items() if k!='source_manifest'}))
    return 0 if proof['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
