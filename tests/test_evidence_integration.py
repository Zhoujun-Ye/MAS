import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.common import evidence as integration
from harness.evidence_mas.store import Store
from harness.evidence_mas.hook import response
from scripts.common.prompts.conditions import condition_instructions
from scripts.studies import benchmark_matrix as matrix


@pytest.mark.parametrize('mode',integration.MODES)
def test_mode_proof_is_source_bound_and_no_output_cap(mode):
    config=integration.configuration(mode)
    assert config['output_cap'] is None and config['monetary_cap'] is None
    integration.validate_proof({'mode':mode,'evidence_configuration':config},mode)
    with pytest.raises(ValueError):integration.validate_proof({'mode':mode,'evidence_configuration':{}},mode)
    assert condition_instructions(SimpleNamespace(evidence_mode=mode),'claude-code-subagents')==''
    assert integration.source_mounts(mode)[0][1]=='/source/harness'


def test_single_and_prompt_override_cannot_enable_evidence():
    with pytest.raises(ValueError):
        integration.validate_condition(SimpleNamespace(evidence_mode='full',backend='claude-code-single-agent'))
    with pytest.raises(ValueError):
        integration.validate_condition(SimpleNamespace(evidence_mode='full',backend='claude-code-subagents',organization_prompt=Path('override')))


def test_matrix_evidence_paths_and_protocol_are_distinct(tmp_path):
    args=SimpleNamespace(root=tmp_path,proofs=tmp_path/'proofs',image='existing',credentials=tmp_path/'private',effort='high',
                         backends=['observations','full'],organization_prompt=None,concurrency=6,judge_concurrency=2)
    protocol=matrix.protocol_settings(args)
    assert protocol['solver_concurrency']==6
    assert protocol['organization_sha256']=={m:integration.configuration(m)['lead_sha256'] for m in args.backends}
    for mode in integration.MODES:
        for benchmark in ('dataclawbench','hybriddeepresearch','kramabench'):
            command=matrix.solver_command(args,benchmark,SimpleNamespace(id='task',web=False),mode,tmp_path/mode)
            assert command[command.index('--backend')+1]=='claude-code-subagents'
            assert command[command.index('--evidence-mode')+1]==mode
            assert command[command.index('--offline-proof')+1]==str(args.proofs/mode/'proof.json')
            assert '--max-budget-usd' not in command


@pytest.mark.parametrize('delegated',[False,True])
def test_audit_reports_delegation_without_compliance_gate(tmp_path,delegated):
    root=tmp_path/'native-profile/evidence';store=Store(root,'benchmark-evidence')
    observation=store.call('obs.capture',dict(tool_name='Bash',tool_input={'command':'fixture'},tool_output='result',
        agent_id='worker' if delegated else 'unknown',status='success',completeness='complete'),role='collector')
    store.call('obs.read',{'obs_id':observation['id']},actor='lead',role='lead')
    if delegated:
        observer=tmp_path/'native-profile/observer/events.jsonl';observer.parent.mkdir()
        observer.write_text('\n'.join(json.dumps({'hook_event_name':kind,'agent_id':'worker'})
                                      for kind in ('SubagentStart','SubagentStop')))
    report=integration.audit(tmp_path,'observations')
    assert report['method_requirements_complete'] is True
    assert report['complete'] is True
    assert report['delegation']['completed_workers'] == int(delegated)
    assert report['audit_policy'] == 'descriptive_only'


def test_continuation_retains_started_slots_without_replacements(tmp_path):
    from common.journal import Journal
    old=tmp_path/'old';old.mkdir()
    tasks=[('kramabench',SimpleNamespace(id='task'),mode,tmp_path/mode) for mode in integration.MODES]
    rows=[dict(benchmark='kramabench',task_id='task',backend=mode,status=status,
               run=str(old/'solvers/kramabench/task'/mode))
          for mode,status in zip(integration.MODES,('interrupted','not_started','not_started'))]
    summary=dict(interrupted=True,authorization={'protocol_settings':{},'task_manifest_sha256':'hash',
        'source_manifest':matrix.runtime.source_manifest()},rows=rows)
    (old/'summary.json').write_text(json.dumps(summary))
    journal=Journal(old/'journal.sqlite')
    row=rows[0];identity=(row['benchmark'],row['task_id'],row['backend'])
    folder=Path(row['run'])/'task'/'claude-code-subagents'
    folder.mkdir(parents=True)
    (folder/'gateway-requests.jsonl').write_text(json.dumps(dict(event='dispatched',upstream_attempted=True)))
    journal.claim('solver',identity,'frozen',row)
    journal.finish('solver',identity,'frozen',row)
    kept=matrix.retained_attempts(old,tasks,{},'hash')
    assert list(kept)==[('kramabench','task','observations')]
    with pytest.raises(ValueError):matrix.retained_attempts(old,tasks,{},'different')
    summary['interrupted']=False
    (old/'summary.json').write_text(json.dumps(summary))
    with pytest.raises(ValueError):matrix.retained_attempts(old,tasks,{},'hash')


def test_audit_requires_no_ceremonial_reads(tmp_path):
    Store(tmp_path / 'native-profile/evidence', 'benchmark-evidence')
    audit = integration.audit(tmp_path, 'full')
    assert audit['complete'] and audit['missing'] == []
    assert audit['delegation']['lead_reads_worker'] is False
    assert audit['audit_policy'] == 'descriptive_only'
    context = response({'hook_event_name': 'PostToolUse'}, {'id': 'obs'})
    assert context == {}


@pytest.mark.parametrize('mode', ['observations', 'full', 'full-prompt-only'])
def test_benchmark_launch_uses_protocol_without_structured_prompt(tmp_path, monkeypatch, mode):
    from harness.evidence_mas import cli
    from scripts.common import evidence
    monkeypatch.setattr(cli, 'run_cli', lambda **kwargs: kwargs)
    result = evidence.launch(mode, 'claude', 'synthetic task', 'shared limits', tmp_path,
        tmp_path, 'fixture-container', model='fixture', allowed_tools=(), disallowed_tools=(), timeout=60)
    from scripts.common.prompts.structured_subagents import PROMPT
    assert result['prompt'] == 'synthetic task\n\nshared limits' + evidence.PROMPT + '\n\n' + cli.workspace_guidance(mode)
    assert PROMPT not in result['prompt']
    argv = result['argv']
    worker = json.loads(argv[argv.index('--agents') + 1])['evidence-worker']
    assert PROMPT not in worker['prompt']
    assert worker['prompt'] == cli.worker_prompt(mode) + '\nShared task rules:\nshared limits'
