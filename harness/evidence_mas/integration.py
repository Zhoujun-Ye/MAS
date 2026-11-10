"""Opt-in native evidence launch shared by existing benchmark workflows."""

import hashlib
import json
from collections import Counter
from pathlib import Path

from .cli import EvidenceMASCLI, lead_prompt, worker_prompt
from .audit import check_workflow
from .store import Store
from .decision import DecisionProtocol, PROTOCOL
from .sharing import POLICY as SHARING_POLICY

MODES = ('observations', 'full', 'full-prompt-only')


def configuration(mode, organization_prompt=''):
    if mode is None:
        return None
    if mode not in MODES:
        raise ValueError('Unknown evidence mode')
    lead = lead_prompt(mode, organization_prompt)
    return dict(mode=mode, protocol=PROTOCOL if mode=='full' else 'observations-v1', lead_sha256=hashlib.sha256(lead.encode()).hexdigest(),
                implementation_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob('*.py')},
                worker_sha256=hashlib.sha256(worker_prompt(mode).encode()).hexdigest(),
                context_sharing=SHARING_POLICY,
                gate_enabled=mode=='full', tool_search=False, monetary_cap=None, output_cap=None)


def validate_condition(args):
    mode = getattr(args,'evidence_mode',None)
    configuration(mode)
    if mode and (args.backend!='claude-code-subagents' or getattr(args,'organization_prompt',None)):
        raise ValueError('Evidence mode requires Subagents without a separate organization override')


def source_mounts(mode):
    return [(Path(__file__).resolve().parents[1],'/source/harness',True)] if mode else []


def launch(mode, executable, prompt, rules, work, folder, identity, *, model, allowed_tools, disallowed_tools, timeout, max_budget_usd=None, organization_prompt='', worker_rules=None):
    configuration(mode)
    if mode == 'full':
        DecisionProtocol(Store(folder/'native-profile/evidence', 'benchmark-evidence')).initialize(prompt)
    return EvidenceMASCLI(str(executable)).run(prompt, model=model, workspace=work, output=folder/'cli',
        task_rules=rules, store_root='/native/evidence',run_id='benchmark-evidence',
        timeout=timeout,execute=True, command_prefix=('docker','exec','-i','--workdir','/workspace',identity),
        observer_target='/native/observer',entrypoint='/source/harness/evidence_mas/entrypoint.py',
        hook_script='/adapter-hooks.py',python='/usr/local/bin/python3',allowed_tools=allowed_tools,
        disallowed_tools=disallowed_tools,max_budget_usd=max_budget_usd,
        settings={'env':{'ENABLE_TOOL_SEARCH':'false'}},mode=mode,organization_prompt=organization_prompt,
        worker_task_rules=worker_rules)


def audit(folder, mode):
    root=folder/'native-profile/evidence'
    if not (root/'store.sqlite').is_file():
        return dict(mode=mode,available=False)
    store=Store(root,'benchmark-evidence',readonly=True)
    report=check_workflow(store,{})
    with store.connect() as db:
        observations=store.latest(db,'observation')
        events=[json.loads(row[0]) for row in db.execute('SELECT body FROM events')]
        report.update(counts={kind:len(store.latest(db,kind)) for kind in ('observation','decision_access','decision_selection')},
                      db_integrity=db.execute('PRAGMA integrity_check').fetchone()[0])
    starts,stops=set(),set()
    native_events=folder/'native-profile/observer/events.jsonl'
    if native_events.is_file():
        for line in native_events.open():
            try:
                event=json.loads(line)
            except ValueError:
                continue
            agent=event.get('agent_id')
            if agent and event.get('hook_event_name')=='SubagentStart':starts.add(agent)
            if agent and event.get('hook_event_name')=='SubagentStop':stops.add(agent)
    completed=starts & stops
    worker_obs={o['id'] for o in observations if o['agent_id'] in completed and o['status']=='success'}
    lead_reads=False
    for event in events:
        if event['role']!='lead':
            continue
        if event['method']=='obs.read':
            lead_reads |= store.read_blob(event['arguments_ref'])['obs_id'] in worker_obs
        elif event['method']=='decision.read':
            result=store.read_blob(event['result_ref'])
            lead_reads |= result.get('observation',{}).get('id') in worker_obs
    report['method_requirements_complete']=report['complete']
    report['delegation']=dict(started_workers=len(starts),completed_workers=len(completed),
                              worker_observations=len(worker_obs),lead_reads_worker=lead_reads)
    report['audit_policy']='descriptive_only'
    report['method_counts']={role:dict(Counter(e['method'] for e in events if e['role']==role))
                             for role in ('lead','worker','collector')}
    deliveries = [store.read_blob(e['result_ref']) for e in events if e['method']=='workspace.context']
    errors = [store.read_blob(e['result_ref']) for e in events if e['method']=='workspace.error']
    report['context_delivery'] = dict(emissions=len(deliveries),
        observation_references=sum(len(d.get('observations',[])) for d in deliveries),
        characters=sum(d.get('characters',0) for d in deliveries),
        scope='Hook emission, not acknowledgement, comprehension or causal use')
    report['workspace_errors'] = dict(count=len(errors),by_tool=dict(Counter(e.get('tool') for e in errors)))
    executions = [o for o in observations if o['tool_name']=='Bash' and o['status']!='unknown']
    overflow = [o for o in executions if o.get('persisted_output_status')]
    report['execution_capture'] = dict(terminal_executions=len(executions),
        by_completeness=dict(Counter(o['completeness'] for o in executions)),
        native_overflow=len(overflow), overflow_snapshots=sum(bool(o.get('persisted_output_ref')) for o in overflow),
        scope='Capture availability, not semantic coverage; overflow artifacts are not reconstructed stdout')
    report['scope']='Workspace integrity and descriptive usage; not delegation compliance, comprehension, or answer correctness'
    report.update(mode=mode,available=True,degraded=(root/'degraded.jsonl').exists())
    report['complete']=bool(report['complete'] and not report['degraded'] and report['db_integrity']=='ok')
    report['condition_status']='workspace_available' if report['complete'] else 'incomplete'
    return report


def validate_proof(proof, mode, organization_prompt=''):
    if mode and (proof.get('mode')!=mode or proof.get('evidence_configuration')!=configuration(mode, organization_prompt)):
        raise ValueError('Evidence proof mode/configuration differs; regenerate the native offline proof')
