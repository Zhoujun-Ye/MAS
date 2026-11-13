"""Krama replay, native wait, timeout and reporting regressions; no providers."""

from datetime import datetime, timedelta, timezone
import json
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from analysis.native_evidence import native_subagents, timeout_waiting_evidence
from harness import ClaudeCodeSingleAgentCLI, ClaudeCodeSubagentsCLI
from harness.runtime_support import runtime
from scripts.kramabench import cli_runtime as krama
from scripts.studies import matched_matrix_report as reports
from benchmarks.kramabench.evaluation import declared_incomplete
from benchmarks.kramabench import evaluation


def test_explicit_unfinished_submission_is_valid_but_not_replayed(tmp_path, monkeypatch):
    work = tmp_path/'workspace'; work.mkdir()
    data = dict(answer=None, pipeline_path=None, evidence='Missing source variable', unfinished=['No answer computed'])
    (work/'submission.json').write_text(json.dumps(data))
    assert krama.submission(work) == data
    def run(command, **kwargs):
        assert command[0] != 'docker'
        return SimpleNamespace(returncode=0, stdout='{}')
    monkeypatch.setattr(krama.subprocess, 'run', run)
    monkeypatch.setattr(krama, 'grade_answer', lambda *a: dict(status='invalid_prediction', score=0, judge_calls=0))
    record = krama.collect_attempt(tmp_path, dict(backend='claude-code-subagents', task_id='fixture', status='cli_exited'),
                                   SimpleNamespace(upstream=tmp_path))
    assert record['pipeline_replay']['status'] == 'incomplete_submission'
    assert record['grade']['score'] == 0 and 'artifact_error' not in record
    assert not (tmp_path/'replay-workspace').exists()


@pytest.mark.parametrize('change', [dict(unfinished=[]), dict(unfinished=[' ']), dict(unfinished=[1]),
                                   dict(answer=1), dict(pipeline_path='missing.py'), dict(extra='field')])
def test_incomplete_contract_does_not_accept_malformed_submissions(change):
    data = dict(answer=None, pipeline_path=None, evidence='', unfinished=['Missing data'])
    data.update(change)
    assert not declared_incomplete(data)


@pytest.mark.parametrize('answer_type', evaluation.METRICS)
def test_unfinished_answers_are_zero_without_a_semantic_judge(tmp_path, monkeypatch, answer_type):
    monkeypatch.setattr(evaluation, 'scoring_contract', lambda *a, **kw: {})
    monkeypatch.setattr(evaluation, 'load_tasks', lambda *a: ([SimpleNamespace(id='fixture', domain='fixture')], {}))
    (tmp_path/'workload').mkdir()
    (tmp_path/'workload/fixture.json').write_text(json.dumps([dict(id='fixture', answer='reference', answer_type=answer_type)]))
    sub = tmp_path/'submission.json'
    sub.write_text(json.dumps(dict(answer=None, pipeline_path=None, evidence='', unfinished=['No answer computed'])))
    result = evaluation.grade_answer(tmp_path, 'fixture', sub,
        paraphrase=lambda *a: pytest.fail('Unfinished submission must not invoke a judge'))
    assert result['status'] == 'incomplete_submission' and result['score'] == 0 and result['judge_calls'] == 0


def test_derived_incomplete_diagnostic_preserves_paid_record(tmp_path):
    folder = tmp_path/'attempt/task/claude-code-subagents'; folder.mkdir(parents=True)
    record = dict(status='cli_exited', pipeline_replay=dict(status='invalid_submission'))
    (folder/'report.json').write_text(json.dumps(record))
    (folder/'submission.json').write_text(json.dumps(dict(answer=None, pipeline_path=None, evidence='', unfinished=['Missing data'])))
    (tmp_path/'summary.json').write_text(json.dumps(dict(run='fixture',
        authorization=dict(effort='none', solver_concurrency=1, judge_concurrency=1),
        rows=[dict(benchmark='kramabench', task_id='task', backend='claude-code-subagents',
                   status='cli_exited', run=str(folder.parents[1]))],
        grades=[dict(benchmark='kramabench', task_id='task', backend='claude-code-subagents',
                     status='graded', grade=dict(status='graded', score=0), judge_calls=0)])))
    before = {p:p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    row = reports.collect(tmp_path)['rows'][0]
    assert row['pipeline_replay_status'] == 'incomplete_submission'
    assert row['recorded_pipeline_replay_status'] == 'invalid_submission' and row['score'] == 0
    assert all(p.read_bytes() == value for p,value in before.items())


@pytest.mark.parametrize('adapter', [ClaudeCodeSingleAgentCLI, ClaudeCodeSubagentsCLI])
def test_native_background_wait_defers_to_shared_outer_deadline(tmp_path, adapter):
    work=tmp_path/'work';work.mkdir()
    plan=adapter().run('task',model='fake',workspace=work,output=tmp_path/'out',timeout=77)
    assert plan['timeout_seconds']==77
    assert plan['environment_overrides']['CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS']=='0'
    assert runtime.native_env(plan['backend'])['CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS']=='0'


def test_system_ceiling_is_not_successful_worker_completion(tmp_path):
    events=tmp_path/'native-profile/observer/events.jsonl';events.parent.mkdir(parents=True)
    events.write_text('\n'.join(map(json.dumps,[dict(hook_event_name='SessionStart',session_id='root'),
        dict(hook_event_name='SubagentStart',agent_id='worker'),dict(hook_event_name='SessionEnd',session_id='root')])))
    report=dict(cli=dict(status='cli_exited',returncode=0,native_result=dict(session_id='root',
        terminal_reason='completed',is_error=False,subagent_stats=dict(spawned=1,completed=0,failed=0,
            killed=dict(parent=0,user=0,system=1)))))
    (tmp_path/'report.json').write_text(json.dumps(report))
    stderr=tmp_path/'cli/stderr.log';stderr.parent.mkdir()
    stderr.write_text('Background tasks still running after 600s; terminating. '
        'Set CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0 to wait indefinitely.\n')
    result=native_subagents(tmp_path)
    assert not result['passed'] and not result['structural_delegation_complete']
    assert result['background_wait_ceiling_exceeded'] and result['worker_termination_accounted']
    stderr.write_text('tool output mentions Background tasks still running after 600s\n')
    assert not native_subagents(tmp_path)['background_wait_ceiling_exceeded']


@pytest.mark.parametrize('code,stdout,status', [(1,b'diagnostic only\n','runtime_error'),
    (0,b'{"answer":1}\n','matched'),(0,b'{"answer":2}\n','answer_mismatch'),
    (0,b'{"answer":1,"extra":2}\n','invalid_output'),(0,b'not json\n','invalid_output'),
    (0,b'','invalid_output'),(None,b'partial\n','timed_out')])
def test_replay_diagnostics_preserve_raw_answer_grade(tmp_path,monkeypatch,code,stdout,status):
    work=tmp_path/'workspace';work.mkdir()
    (work/'pipeline.py').write_text('print(1)')
    (work/'submission.json').write_text(json.dumps(dict(answer=1,pipeline_path='pipeline.py',evidence='',unfinished=[])))
    def run(command,**kw):
        if command[:2]==['docker','ps']:return SimpleNamespace(returncode=0,stdout='')
        if command[:2]==['docker','run']:
            if code is None:raise subprocess.TimeoutExpired(command,1,output=stdout,stderr=b'partial error')
            return SimpleNamespace(returncode=code,stdout=stdout,stderr=b'Worksheet not found' if code else b'')
        if command[:2]==['docker','inspect']:
            return SimpleNamespace(returncode=0,stdout=json.dumps(dict(Status='exited',Running=False,
                StartedAt='2026-11-12T00:00:00Z',Error='',ExitCode=code)))
        return SimpleNamespace(returncode=0,stdout='{}')
    monkeypatch.setattr(krama.subprocess,'run',run)
    monkeypatch.setattr(krama,'grade_answer',lambda *a:dict(status='graded',score=1,judge_calls=0))
    r=krama.collect_attempt(tmp_path,dict(backend='claude-code-subagents',task_id='fixture',status='cli_exited'),
        SimpleNamespace(upstream=tmp_path,image='fixture',replay_timeout=1))
    assert r['pipeline_replay']['status']==status and r['grade']['score']==1
    if code==1:
        assert r['artifact_error']['type']=='PipelineExecutionError'
        assert (tmp_path/'pipeline-stderr.log').read_bytes()==b'Worksheet not found'


def test_missing_submission_is_not_an_observed_pipeline_success(tmp_path,monkeypatch):
    monkeypatch.setattr(krama.subprocess,'run',lambda *a,**kw:SimpleNamespace(returncode=0,stdout='{}'))
    monkeypatch.setattr(krama,'grade_answer',lambda *a:dict(status='invalid_submission',score=0))
    r=krama.collect_attempt(tmp_path,dict(backend='claude-code-subagents',task_id='fixture',status='cli_exited'),
        SimpleNamespace(upstream=tmp_path))
    assert r['pipeline_replay']['status']=='missing_submission' and r['grade']['score']==0


@pytest.mark.parametrize('execution_status', ['matched','runtime_error','timed_out'])
def test_replay_cleanup_failure_is_harness_failure_not_model_blame(tmp_path,monkeypatch,execution_status):
    work=tmp_path/'workspace';work.mkdir()
    (work/'pipeline.py').write_text('print(1)')
    (work/'submission.json').write_text(json.dumps(dict(answer=1,pipeline_path='pipeline.py',evidence='',unfinished=[])))
    def execute(command, **kwargs):
        if command[:2]==['docker','run']:
            if execution_status=='timed_out':raise subprocess.TimeoutExpired(command,1)
            return SimpleNamespace(returncode=int(execution_status=='runtime_error'),stdout=b'{"answer":1}\n',stderr=b'')
        return SimpleNamespace(returncode=0,stdout='{}')
    def fail(name):raise RuntimeError('Synthetic daemon removal failure')
    monkeypatch.setattr(krama.subprocess,'run',execute)
    monkeypatch.setattr(krama.runtime,'remove_named_container',fail)
    monkeypatch.setattr(krama,'replay_failure',lambda *a:dict(status='runtime_error',execution_origin='container_process'))
    monkeypatch.setattr(krama,'grade_answer',lambda *a:dict(status='graded',score=1,judge_calls=0))
    record=krama.collect_attempt(tmp_path,dict(backend='claude-code-subagents',task_id='fixture',status='cli_exited'),
                                 SimpleNamespace(upstream=tmp_path,image='fixture',replay_timeout=1))
    assert record['pipeline_replay']['status']=='harness_error'
    assert record['pipeline_replay']['stage']=='cleanup'
    assert record['pipeline_replay']['execution_status']==execution_status
    assert record['replay_cleanup']['removed'] is False
    assert record['grade']['score']==1
    if execution_status=='runtime_error':
        assert record['pipeline_replay']['execution_error']['type']=='PipelineExecutionError'


def test_historical_pipeline_diagnostics_do_not_change_scores():
    assert reports.pipeline_diagnostic(dict(pipeline_exit_code=1))=='runtime_error'
    assert reports.pipeline_diagnostic(dict(pipeline_exit_code=0,pipeline_answer_matches_submission=False))=='answer_mismatch'
    assert reports.pipeline_diagnostic({}) is None


def test_corrected_export_keeps_raw_audit_and_grade_without_mutating_evidence(tmp_path):
    folder=tmp_path/'attempt/task/claude-code-subagents';folder.mkdir(parents=True)
    native=dict(session_id='root',terminal_reason='completed',is_error=False,
        subagent_stats=dict(spawned=1,completed=0,failed=0,killed=dict(parent=0,user=0,system=1)))
    record=dict(status='cli_exited',subagents_audit=dict(passed=True),
        cli=dict(status='cli_exited',returncode=0,native_result=native),pipeline_exit_code=1)
    (folder/'report.json').write_text(json.dumps(record))
    (folder.parents[1]/'summary.json').write_text(json.dumps(dict(rows=[record])))
    events=folder/'native-profile/observer/events.jsonl';events.parent.mkdir(parents=True)
    events.write_text('\n'.join(map(json.dumps,[dict(hook_event_name='SessionStart',session_id='root'),
        dict(hook_event_name='SubagentStart',agent_id='worker'),dict(hook_event_name='SessionEnd',session_id='root')])))
    (folder/'cli').mkdir()
    (folder/'cli/stderr.log').write_text('Background tasks still running after 600s; terminating. '
        'Set CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0 to wait indefinitely.\n')
    (tmp_path/'summary.json').write_text(json.dumps(dict(run='fixture',
        authorization=dict(effort='none',solver_concurrency=1,judge_concurrency=1),
        rows=[dict(benchmark='kramabench',task_id='task',backend='claude-code-subagents',
                   status='cli_exited',run=str(folder.parents[1]))],
        grades=[dict(benchmark='kramabench',task_id='task',backend='claude-code-subagents',
                     status='graded',grade=dict(status='graded',score=1),judge_calls=0)])))
    before={p:p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    report=reports.collect(tmp_path);row=report['rows'][0]
    assert row['recorded_native_audit_passed'] is True and row['native_audit_passed'] is False
    assert row['native_wait_ceiling_exceeded'] and row['pipeline_replay_status']=='runtime_error'
    assert row['score']==1 and report['groups'][0]['raw_accuracy']==1
    reports.write_report(report,tmp_path/'export')
    assert 'Single-Policy Mean' in (tmp_path/'export/REPORT.md').read_text()
    assert 'Pipeline Diagnostics' in (tmp_path/'export/REPORT.md').read_text()
    assert all(p.read_bytes()==value for p,value in before.items())


@pytest.mark.parametrize('code',[125,126,127,1])
@pytest.mark.parametrize('started',[True,False,None])
def test_docker_failure_is_not_a_model_error_without_execution_evidence(monkeypatch,code,started):
    def inspect(*a,**kw):
        if started is None:raise subprocess.TimeoutExpired(a[0],15)
        return SimpleNamespace(returncode=0,stdout=json.dumps(dict(Status='exited' if started else 'created',
            Running=False,StartedAt='2026-11-12T00:00:00Z' if started else '0001-01-01T00:00:00Z',
            Error='' if started else 'failed to create mount',ExitCode=code)))
    monkeypatch.setattr(krama.subprocess,'run',inspect)
    d=krama.replay_failure('owned-container',code)
    assert d['status']==('runtime_error' if started is True else 'harness_error')
    assert d['execution_origin']==('container_process' if started is True else 'docker_or_unverified')


def test_historical_reserved_exit_is_unknown_not_a_model_failure():
    assert reports.pipeline_diagnostic(dict(pipeline_exit_code=125))=='execution_origin_unverified'
    assert reports.pipeline_diagnostic(dict(pipeline_exit_code=125,pipeline_replay=dict(status='runtime_error')))=='runtime_error'


def hook_fixture(folder,cutoff):
    path=folder/'native-profile/observer/events.jsonl';path.parent.mkdir(parents=True)
    data=[dict(hook_event_name='SessionStart',session_id='root',offset=-3),
          dict(hook_event_name='SubagentStart',session_id='root',agent_id='worker',offset=-2),
          dict(hook_event_name='Stop',session_id='root',offset=-1),
          dict(hook_event_name='SubagentStop',session_id='root',agent_id='worker',offset=1),
          dict(hook_event_name='SessionEnd',session_id='root',offset=2)]
    for e in data:e['observer_received_at']=(cutoff+timedelta(seconds=e.pop('offset'))).isoformat()
    path.write_text('\n'.join(map(json.dumps,data)))
    return path,data


def test_timeout_hook_state_ignores_cleanup_after_deadline(tmp_path):
    cutoff=datetime.now(timezone.utc);path,rows=hook_fixture(tmp_path,cutoff)
    d=timeout_waiting_evidence(tmp_path,cutoff.isoformat())
    assert d['measured'] and d['lead_idle_waiting'] and d['pending_worker_ids']==['worker']
    rows.insert(3,dict(hook_event_name='PreToolUse',session_id='root',observer_received_at=cutoff.isoformat()))
    path.write_text('\n'.join(map(json.dumps,rows)))
    assert timeout_waiting_evidence(tmp_path,cutoff.isoformat())['lead_idle_waiting'] is False
    rows[0].pop('observer_received_at');path.write_text('\n'.join(map(json.dumps,rows)))
    assert timeout_waiting_evidence(tmp_path,cutoff.isoformat())['lead_idle_waiting'] is None
    assert timeout_waiting_evidence(tmp_path,None)['measured'] is False


@pytest.mark.parametrize('timing',['before','after','unknown'])
def test_timeout_submission_diagnostic_never_changes_zero_primary_score(tmp_path,monkeypatch,timing):
    work=tmp_path/'workspace';work.mkdir()
    (work/'pipeline.py').write_text('print(1)')
    sub=work/'submission.json';sub.write_text(json.dumps(dict(answer=1,pipeline_path='pipeline.py',evidence='',unfinished=[])))
    cutoff=datetime.now(timezone.utc)+timedelta(seconds=1)
    hook_fixture(tmp_path,cutoff)
    if timing=='after':os.utime(sub,(cutoff.timestamp()+10,cutoff.timestamp()+10))
    def run(cmd,**kw):
        if cmd[:2]==['docker','ps']:return SimpleNamespace(returncode=0,stdout='')
        if cmd[:2]==['docker','run']:return SimpleNamespace(returncode=0,stdout=b'{"answer":1}\n',stderr=b'')
        return SimpleNamespace(returncode=0,stdout='{}')
    monkeypatch.setattr(krama.subprocess,'run',run)
    monkeypatch.setattr(krama,'grade_answer',lambda *a:dict(status='graded',score=1,judge_calls=0))
    cli=dict(status='timed_out')
    if timing!='unknown':cli['timeout_observed_at']=cutoff.isoformat()
    r=krama.collect_attempt(tmp_path,dict(task_id='fixture',backend='claude-code-subagents',status='timed_out',cli=cli),
                            SimpleNamespace(upstream=tmp_path,image='fixture'))
    assert r['grade']['score']==0 and r['artifact_grade']['score']==1
    assert r['timeout_diagnostic']['lead_waiting_with_valid_submission'] is {
        'before':True,'after':False,'unknown':None}[timing]


def test_real_stub_timeout_records_host_boundary_before_cleanup(tmp_path):
    work=tmp_path/'work';work.mkdir();script=tmp_path/'stub'
    script.write_text(f'#!{sys.executable}\nimport sys,time\nif "--version" in sys.argv:\n print("2.1.286 (Claude Code)")\nelse:\n time.sleep(60)\n')
    script.chmod(0o755)
    r=ClaudeCodeSubagentsCLI(str(script)).run('task',model='fake',workspace=work,output=tmp_path/'out',execute=True,timeout=.05)
    assert r['status']=='timed_out'
    assert datetime.fromisoformat(r['timeout_observed_at'])>=datetime.fromisoformat(r['native_started_at'])


def row(task,backend,audit=True):
    return dict(benchmark='kramabench',task_id=task,backend=backend,native_audit_passed=audit,score=1,
                status='cli_exited',seconds=1,total_usd_offpeak=.1,model_requests=1)


def test_paired_audit_view_removes_tasks_from_all_conditions_without_touching_raw():
    conditions=('claude-code-single-agent','native','claude-code-subagents')
    rows=[row(t,c) for t in ('clean','failed','unknown') for c in conditions]
    rows[4]['native_audit_passed']=False;rows[8]['native_audit_passed']=None
    before=json.dumps(rows,sort_keys=True)
    view=reports.paired_audit_view(rows)
    assert view['status']=='available' and view['excluded_attempts']==6
    assert {e['task_id'] for e in view['excluded_tasks']}=={'failed','unknown'}
    assert all(g['attempts']==1 and g['raw_accuracy']==1 for g in view['groups'])
    assert json.dumps(rows,sort_keys=True)==before


def test_paired_view_requires_complete_authorized_pairs():
    rows=[row('a','native'),row('a','claude-code-single-agent')]
    auth=dict(selections=[dict(benchmark='kramabench',task_id=t,backend=c) for t in ('a','missing')
                          for c in ('native','claude-code-single-agent','claude-code-subagents')])
    v=reports.paired_audit_view(rows,auth)
    assert v['status']=='available' and len(v['excluded_tasks'])==2 and v['groups']==[]
    assert reports.paired_audit_view(rows+[rows[0]])['status']=='unavailable'


def test_partial_cost_display_uses_all_known_requests_not_only_complete_attempts():
    a=row('a','native');a.update(model_usd_offpeak=.1,known_model_usd_offpeak_subtotal=.1,
        web_usd_estimate=0,judge_usd_offpeak=0,requests_with_unknown_cost=0)
    b=row('b','native');b.update(total_usd_offpeak=None,model_usd_offpeak=None,known_model_usd_offpeak_subtotal=.115,
        web_usd_estimate=0,judge_usd_offpeak=.001,requests_with_unknown_cost=1)
    g=reports.summarize([a,b])[0]
    assert g['total_usd_offpeak'] is None and g['known_model_usd_offpeak_subtotal']==pytest.approx(.215)
    assert reports.cost_display(g)=='>= $0.216000 (1 unknown model request)'
    assert reports.cost_display(dict(total_usd_offpeak=None,known_total_usd_offpeak_subtotal=None))=='unknown'
    assert reports.cost_display(dict(total_usd_offpeak=None,known_total_usd_offpeak_subtotal=0))=='unknown'
