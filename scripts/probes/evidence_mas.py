"""Pinned Claude lead/worker hooks + MCP probe, synthetic provider only."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import secrets
import shlex
import subprocess
import sys
import threading
from unittest.mock import patch
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from analysis.native_evidence import native_subagents
from benchmarks._external import digest
from common.io import write_json
from harness.evidence_mas.cli import EvidenceMASCLI
from harness.evidence_mas.store import Store
from harness.evidence_mas.decision import DecisionProtocol
from harness.evidence_mas.measurements import measurement
from scripts.common.evidence import configuration, PROMPT
from harness.runtime_support import credential_gateway
from harness.runtime_support import runtime
from scripts.probes.offline_gateway import Response, sse


def decoded(value):
    if isinstance(value, str):
        try:
            yield from decoded(json.loads(value))
        except (ValueError, RecursionError):
            return
    elif isinstance(value, dict):
        yield value
        for child in value.values():
            yield from decoded(child)
    elif isinstance(value, list):
        for child in value:
            yield from decoded(child)


class Fixture:
    def __init__(self, mode='full'):
        self.mode = mode
        self.requests, self.errors = [], []
        self.lock = threading.Lock()

    def respond(self, request):
        body = json.loads(request.data)
        if urlsplit(request.full_url).path.endswith('count_tokens'):
            return Response(b'{"input_tokens":100}', 'application/json')
        with self.lock:
            if len(self.requests) >= 48:
                raise ValueError('Synthetic request ceiling exceeded')
            self.requests.append(body)
            block = self.next(body)
            number = len(self.requests)
        stop = 'tool_use' if block['type'] == 'tool_use' else 'end_turn'
        response = dict(id='fixture-'+str(number), type='message', role='assistant', model=body['model'],
            content=[block], stop_reason=stop, stop_sequence=None,
            usage=dict(input_tokens=100, output_tokens=10, cache_creation_input_tokens=0, cache_read_input_tokens=0))
        if not body.get('stream'):
            return Response(json.dumps(response).encode(), 'application/json')
        start = dict(block, **({'input': {}} if block['type'] == 'tool_use' else {'text': ''}))
        delta = dict(type='input_json_delta', partial_json=json.dumps(block['input'])) if block['type'] == 'tool_use' else dict(type='text_delta', text=block['text'])
        return sse([dict(type='message_start', message=dict(response, content=[], stop_reason=None)),
            dict(type='content_block_start', index=0, content_block=start),
            dict(type='content_block_delta', index=0, delta=delta), dict(type='content_block_stop', index=0),
            dict(type='message_delta', delta=dict(stop_reason=stop, stop_sequence=None), usage=dict(output_tokens=10)),
            dict(type='message_stop')])

    def next(self, body):
        if self.mode == 'full':
            return self.decision_next(body)
        worker = any(t.get('name', '').startswith('mcp__evidence_worker__') for t in body.get('tools', []))
        role = 'worker' if worker else 'lead'
        prefix = 'mcp__evidence_worker__' if worker else 'mcp__evidence__'
        results = {}
        for message in body.get('messages', []):
            for block in message.get('content', []) if isinstance(message.get('content'), list) else []:
                if block.get('type') == 'tool_result':
                    results[block['tool_use_id']] = block
                    if block.get('is_error'):
                        self.errors.append(dict(role=role, result=block))
        def tool(step, name, arguments):
            return dict(type='tool_use', id=f'fixture-{role}-{step}', name=name, input=arguments)
        def data(step, predicate):
            return next((v for v in decoded(results.get(f'fixture-{role}-{step}', {})) if predicate(v)), None)
        def done(step):
            return f'fixture-{role}-{step}' in results
        if any(k.startswith(f'fixture-{role}-') and v.get('is_error') for k, v in results.items()):
            return dict(type='text', text='Offline probe encountered a tool error; preserve evidence.')
        if not done('shell'):
            return tool('shell', 'Bash', dict(command='printf '+role+'-observation', description='Synthetic observation'))
        if not done('list'):
            return tool('list', prefix+'obs_list', dict(filters={'tool_call_id': f'fixture-{role}-shell'}))
        listed = data('list', lambda v: isinstance(v.get('items'), list))
        if not listed or not listed['items']:
            return dict(type='text', text='No hook observation found.')
        obs_id = listed['items'][0]['id']
        if not done('read'):
            return tool('read', prefix+'obs_read', dict(obs_id=obs_id))
        if self.mode in ('observations', 'full-prompt-only'):
            if worker:
                return dict(type='text', text='Worker completed raw observation sharing.')
            if not done('delegate'):
                return tool('delegate', 'Agent', dict(description='Verify raw observation sharing',
                    subagent_type='evidence-worker', prompt='Use synthetic local tools only; read your observation and return its reference.'))
            lists = [key for key in results if key.startswith('fixture-lead-crosslist')]
            cross = next((v for v in decoded(results[lists[-1]]) if isinstance(v.get('items'), list)), None) if lists else None
            if not lists or ((not cross or not cross['items']) and 'Worker completed raw observation sharing.' in json.dumps(body['messages'])):
                return tool('crosslist-'+str(len(lists)), prefix+'obs_list', dict(filters={'tool_call_id': 'fixture-worker-shell'}))
            if not cross or not cross['items']:
                return dict(type='text', text='Await native worker completion notification.')
            if not done('crossread'):
                return tool('crossread', prefix+'obs_read', dict(obs_id=cross['items'][0]['id']))
            if not done('trace'):
                return tool('trace', prefix+'workspace_trace', dict(object_id=cross['items'][0]['id']))
            return dict(type='text', text='Raw observation sharing complete.')
    def decision_next(self, body):
        worker = any(t.get('name', '').startswith('mcp__evidence_worker__') for t in body.get('tools', []))
        role = 'worker' if worker else 'lead'
        prefix = 'mcp__evidence_worker__' if worker else 'mcp__evidence__'
        results = {b['tool_use_id']: b for m in body.get('messages', [])
                   for b in m.get('content', []) if isinstance(b, dict) and b.get('type') == 'tool_result'}
        def tool(step, name, arguments):
            return dict(type='tool_use', id=f'fixture-{role}-{step}', name=name, input=arguments)
        def done(step):
            return f'fixture-{role}-{step}' in results
        if any(v.get('is_error') for key,v in results.items() if key!='fixture-lead-completed-wait'):
            self.errors.append(dict(role=role, error='decision_fixture_tool_error'))
            return dict(type='text', text='Decision fixture failed.')
        if not done('shell'):
            value = 2 if worker else 1
            measured = measurement(value, dict(quantity='fixture value',statistic='mean',population='fixture',
                period='not_applicable',unit='count',dataset='fixture-v1'), {'option':role}, answer_target=True)
            return tool('shell', 'Bash', dict(command="printf '%s\\n' " + shlex.quote(json.dumps(measured)), description='Synthetic typed measurement'))
        if worker:
            if not done('overflow'):
                return tool('overflow', 'Bash', dict(command="python -c 'print(\"x\" * 40000); print(\"native-overflow-tail\")'",
                    description='Synthetic native overflow capture'))
            if not done('view'):
                return tool('view', prefix+'decision_view', {})
            return dict(type='text', text='Decision worker finished.')
        if not done('delegate'):
            return tool('delegate', 'Agent', dict(description='Synthetic decision result', subagent_type='evidence-worker', prompt='Run synthetic computation and report.'))
        views = [k for k in results if k.startswith('fixture-lead-view-')]
        view = next((v for v in decoded(results[views[-1]]) if 'candidates' in v), None) if views else None
        if not views:
            return tool('view-0', prefix+'decision_view', {})
        if not view or len(view['candidates']) < 2:
            if 'Decision worker finished.' in json.dumps(body['messages']):
                return tool('view-'+str(len(views)), prefix+'decision_view', {})
            return dict(type='text', text='Await native completion notification.')
        candidate = next(c for c in view['candidates'] if c['value'] == 2)
        if not done('overflow-list'):
            return tool('overflow-list', prefix+'obs_list', dict(filters={'tool_call_id':'fixture-worker-overflow'}))
        listed = next((v for v in decoded(results['fixture-lead-overflow-list']) if isinstance(v.get('items'),list)), None)
        if not listed or not listed['items']:
            self.errors.append(dict(role=role, error='native_overflow_missing'))
            return dict(type='text', text='Native overflow fixture missing.')
        if not done('overflow-read'):
            return tool('overflow-read', prefix+'obs_read', dict(obs_id=listed['items'][0]['id'],
                field='persisted_output', start=39990, limit=100))
        for item in view['candidates']:
            key = 'read-'+item['id']
            if not done(key):
                return tool(key, prefix+'decision_read', {'candidate_id':item['id']})
        if not done('select'):
            return tool('select', prefix+'decision_select', dict(snapshot=view['snapshot'], candidate_id=candidate['id'],
                basis={'task_quote':'Verify hooks and shared MCP', 'criterion':'Synthetic fixture requires the worker result'},
                comparisons={c['id']:'Lead value is the synthetic alternative' for c in view['candidates'] if c['id'] != candidate['id']}))
        if not done('check'):
            return tool('check', prefix+'decision_check', {'submission':{'answer':2}})
        if not done('completed-wait'):
            return tool('completed-wait', 'Bash', {'command':'sleep 0.01; echo waited',
                                                  'description':'Wait for completed subagent'})
        return dict(type='text', text='Decision fixture complete.')


def probe(root, image, mode='full', fixture=None, key=None):
    work, profile = root/'workspace', root/'native-profile'
    work.mkdir(parents=True)
    (profile/'home').mkdir(parents=True)
    fixture = fixture or Fixture(mode)
    if mode == 'full':
        DecisionProtocol(Store(profile/'evidence', 'native-offline')).initialize('Verify hooks and shared MCP with one evidence-worker.')
    key = key or 'synthetic-' + secrets.token_hex(24)
    source = Path(__file__).resolve().parents[2]
    proof = dict(passed=False, mode=mode, backend='claude-code-subagents', requested_effort='high',
                 evidence_configuration=configuration(mode), paid_calls=0, real_credentials=False, network='none', concurrency=1,
                 runtime_binding=dict(image_id=image, binary_sha256=digest(runtime.CLAUDE)))
    identity = None
    gateway = None
    try:
        # The caller installs one strict dispatcher before starting any probe threads.
        gateway = credential_gateway.CredentialGateway(key, unix_path=root/'gateway.sock')
        gateway.__enter__()
        identity = runtime.container(work, profile, work, image, network='none', gateway=gateway,
            dataset_mounts=[(source/'harness', '/source/harness', True)], effort='high')
        result = EvidenceMASCLI(str(runtime.CLAUDE)).run('Verify hooks and shared MCP with one evidence-worker.',
            model='deepseek-flash[1m]', workspace=work, output=root/'cli', store_root='/native/evidence',
            run_id='native-offline', task_rules='Use synthetic local data only. No network, installs or paid calls.',
            timeout=180, execute=True, command_prefix=('docker', 'exec', '-i', '--workdir', '/workspace', identity),
            observer_target='/native/observer', entrypoint='/source/harness/evidence_mas/entrypoint.py',
            hook_script='/adapter-hooks.py', python='/usr/local/bin/python3',
            allowed_tools=('Bash', 'Read', 'Agent'), settings={'env': {'ENABLE_TOOL_SEARCH': 'false'}},
            mode=mode, organization_prompt=PROMPT)
        proof['cli_status'] = result['status']
        proof['native_subagents'] = native_subagents(root)
        store = Store(profile/'evidence', 'native-offline')
        with store.connect() as db:
            observations = store.latest(db, 'observation')
            events = [json.loads(r[0]) for r in db.execute('SELECT body FROM events')]
        proof['lead_observation'] = any(o['tool_call_id']=='fixture-lead-shell' and o['status']=='success' for o in observations)
        proof['worker_observation'] = any(o['tool_call_id']=='fixture-worker-shell' and o['status']=='success' and o['agent_id']!='unknown' for o in observations)
        worker_requests = [b for b in fixture.requests if any(t.get('name','').startswith('mcp__evidence_worker__') for t in b.get('tools',[]))]
        proof['request_effort_verified'] = bool(fixture.requests) and all(b.get('output_config',{}).get('effort')=='high' for b in fixture.requests)
        proof['max_output_tokens_observed'] = sorted({b.get('max_tokens') for b in fixture.requests if b.get('max_tokens') is not None})
        proof['worker_selection_not_exposed'] = bool(worker_requests) and all(
            not any(t['name'].endswith(('__decision_select','__decision_check')) for t in b.get('tools',[])) for b in worker_requests)
        proof['degraded'] = (profile/'evidence/degraded.jsonl').exists()
        def strings(value):
            if isinstance(value,str):
                yield value
            elif isinstance(value,(dict,list)):
                for child in value.values() if isinstance(value,dict) else value:
                    yield from strings(child)
        proof['cross_context_in_native_request'] = {}
        for role in ('lead','worker'):
            requests = worker_requests if role=='worker' else [b for b in fixture.requests if b not in worker_requests]
            foreign = {o['id'] for o in observations if o['tool_call_id']=='fixture-'+('worker' if role=='lead' else 'lead')+'-shell'}
            proof['cross_context_in_native_request'][role] = any(
                'UNTRUSTED shared observations' in text and any(identity in text for identity in foreign)
                for body in requests for text in strings(body))
        proof['context_emissions'] = sum(e['method']=='workspace.context' for e in events)
        proof['workspace_errors'] = sum(e['method']=='workspace.error' for e in events)
        if mode=='full':
            protocol = DecisionProtocol(store)
            overflow = [o for o in observations if o['tool_call_id']=='fixture-worker-overflow']
            overflow_ids = {o['id'] for o in overflow}
            proof['native_overflow_capture'] = bool(overflow) and all(
                o['completeness']=='pointer' and o.get('persisted_output_status')=='captured'
                and store.read_blob(o['persisted_output_ref']).endswith('native-overflow-tail\n') for o in overflow)
            proof['native_overflow_tail_read'] = any(e['method']=='obs.read' and e['role']=='lead'
                and store.read_blob(e['arguments_ref']).get('obs_id') in overflow_ids
                and store.read_blob(e['arguments_ref']).get('field')=='persisted_output'
                and 'native-overflow-tail' in store.read_blob(e['result_ref'])['text'] for e in events)
            proof['decision_check'] = protocol.check({'answer':2})
            proof['decision_mismatch_rejected'] = not protocol.check({'answer':1})['accepted']
            proof['lead_execution_reads'] = sum(e['method']=='decision.read' and e['role']=='lead' for e in events)
            proof['completed_worker_wait_denied'] = (any(e['method']=='workspace.wait_blocked' for e in events)
                and not any(o['tool_call_id']=='fixture-lead-completed-wait' and o['status']=='success' for o in observations))
            mechanism_passed = (proof['decision_check']['accepted'] and proof['decision_mismatch_rejected']
                                and proof['lead_execution_reads']>=2 and proof['completed_worker_wait_denied']
                                and proof['native_overflow_capture'] and proof['native_overflow_tail_read'])
        else:
            proof['role_reads'] = {role:any(e['method']=='obs.read' and e['role']==role for e in events) for role in ('lead','worker')}
            foreign = {o['id'] for o in observations if o['tool_call_id']=='fixture-worker-shell'}
            proof['lead_reads_worker_observation'] = any(e['method']=='obs.read' and e['role']=='lead' and
                store.read_blob(e['arguments_ref'])['obs_id'] in foreign for e in events)
            proof['trace_verified'] = any(e['method']=='workspace.trace' for e in events)
            mechanism_passed = all(proof['role_reads'].values()) and proof['lead_reads_worker_observation'] and proof['trace_verified']
        proof['passed'] = bool(result['status']=='cli_exited' and proof['native_subagents']['passed']
            and proof['lead_observation'] and proof['worker_observation'] and proof['worker_selection_not_exposed']
            and all(proof['cross_context_in_native_request'].values()) and mechanism_passed
            and not proof['degraded'] and not proof['workspace_errors'] and not fixture.errors)
    except Exception as exc:
        proof.update(error_type=type(exc).__name__, error=str(exc))
    finally:
        if identity:
            try:
                runtime.stop_container(identity)
            finally:
                subprocess.run(['docker', 'rm', '-f', identity], check=True, capture_output=True)
            proof['container_removed'] = True
        if gateway:
            gateway.__exit__(None, None, None)
        proof['fake_model_requests'] = len(fixture.requests)
        write_json(root/'fake-provider-requests.json', fixture.requests)
        write_json(root/'tool-errors.json', fixture.errors)
        write_json(root/'proof.json', proof)
    return proof


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--image', default='mas/research-benchmarks:20261103-v1')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--mode', choices=('full', 'observations', 'full-prompt-only', 'both'), default='both')
    args = parser.parse_args()
    if not args.execute:
        count = 2 if args.mode == 'both' else 1
        print(json.dumps(dict(status='planned', paid_calls=0, conditions=count, concurrency=count)))
        return 0
    import os
    os.umask(0o077)
    args.output.mkdir(parents=True, exist_ok=False)
    image = json.loads(subprocess.check_output(['docker', 'image', 'inspect', args.image]))[0]['Id']
    modes = ('full', 'observations') if args.mode == 'both' else (args.mode,)
    fixtures = {'synthetic-'+secrets.token_hex(24): Fixture(mode) for mode in modes}
    def fake(request):
        key = request.get_header('Authorization', '').removeprefix('Bearer ')
        if key not in fixtures or not request.full_url.startswith('https://api.deepseek.com/'):
            raise ValueError('Unknown synthetic upstream request')
        return fixtures[key].respond(request)
    with patch.object(credential_gateway, 'open_upstream', fake):
        with ThreadPoolExecutor(max_workers=len(modes)) as pool:
            futures = [pool.submit(probe, args.output.resolve()/fixture.mode, image, fixture.mode, fixture, key)
                       for key, fixture in fixtures.items()]
            results = [f.result() for f in futures]
    summary = dict(passed=all(p['passed'] for p in results), paid_calls=0, concurrency=len(modes), results=results)
    write_json(args.output/'summary.json', summary)
    print(json.dumps(summary))
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
