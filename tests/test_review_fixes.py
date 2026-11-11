"""Regression coverage for the November 11 infrastructure review; no providers."""

import json
import sqlite3
import threading
from types import SimpleNamespace

import pytest

from harness import ClaudeCodeSingleAgentCLI, ClaudeCodeSubagentsCLI
from harness._claude_hooks import SINGLE_TOOLS, SUBAGENT_TOOLS
from harness.runtime_support import runtime, web_fetch
from harness.runtime_support.admission import infrastructure_health
from harness.runtime_support.proof import validate_runtime, validate_surface
from harness.runtime_support.tools import run_sql


def test_shared_surface_diff_is_only_native_delegation():
    single = ClaudeCodeSingleAgentCLI().command('fixture')
    sub = ClaudeCodeSubagentsCLI().command('fixture')
    a = set(single[single.index('--tools') + 1].split(','))
    b = set(sub[sub.index('--tools') + 1].split(','))
    assert a == set(SINGLE_TOOLS)
    assert b - a == {'Agent', 'Task', 'SendMessage', 'ListAgents'}
    assert a <= b and '--disable-slash-commands' in sub
    assert set(runtime.options('claude-code-subagents')['allowed_tools']) == b


@pytest.mark.parametrize('backend', ['claude-code-single-agent', 'claude-code-subagents'])
def test_worker_aliases_and_bash_limits_are_identical(backend):
    env = runtime.native_env(backend)
    assert all(env[f'ANTHROPIC_DEFAULT_{alias}_MODEL'] == 'deepseek-flash[1m]'
               for alias in ('OPUS', 'SONNET', 'HAIKU', 'FABLE'))
    assert env['BASH_DEFAULT_TIMEOUT_MS'] == env['BASH_MAX_TIMEOUT_MS'] == '600000'
    assert env['CLAUDE_CODE_MAX_RETRIES'] == '0'


@pytest.mark.parametrize('field,value', [('tools', ['Bash']), ('skills', ['deep-research']),
    ('slash_commands', ['loop']), ('skills', None)])
def test_proof_rejects_missing_or_extra_native_surface(field, value):
    surface = dict(tools=list(SUBAGENT_TOOLS), skills=[], slash_commands=[])
    validate_surface(surface, 'claude-code-subagents')
    surface[field] = value
    with pytest.raises(ValueError, match='surface'):
        validate_surface(surface, 'claude-code-subagents')


def test_old_environment_proof_cannot_admit_new_configuration():
    from test_proof_binding import claude_proof
    proof = claude_proof()
    proof['runtime_configuration_sha256'] = 'old'
    with pytest.raises(ValueError, match='configuration changed'):
        validate_runtime(proof, 'claude-code-single-agent', 'sha256:image', 'binary-hash')


def test_only_authoritative_upstream_5xx_marks_degradation(tmp_path):
    path = tmp_path / 'gateway-requests.jsonl'
    assert infrastructure_health(path)['infra_degraded'] is None
    rows = [dict(event='finished', request_id='worker', upstream_attempted=True,
                 route='/anthropic/v1/messages', http_status=503, outcome='upstream_rejected'),
            dict(event='finished', request_id='local', upstream_attempted=False,
                 http_status=502, outcome='rejected'),
            dict(event='finished', request_id='unknown', upstream_attempted=True,
                 http_status=502, outcome='transport_error')]
    path.write_text('\n'.join(map(json.dumps, [*rows, rows[0]])))
    health = infrastructure_health(path)
    assert health['infra_degraded'] is True
    assert health['upstream_5xx'] == [dict(request_id='worker', http_status=503, route='/anthropic/v1/messages')]
    path.write_text(json.dumps(rows[1]))
    assert infrastructure_health(path)['infra_degraded'] is False
    path.write_text('{partial')
    assert infrastructure_health(path)['infra_degraded'] is None


@pytest.mark.parametrize('status', ['cli_exited', 'timed_out', 'cli_error'])
@pytest.mark.parametrize('backend', ['claude-code-single-agent', 'claude-code-subagents'])
def test_krama_quiesces_before_audit_and_preserves_failure_status(tmp_path, monkeypatch, status, backend):
    from benchmarks.kramabench.tasks import Task
    from scripts.kramabench import cli_runtime as krama
    state = []
    class Gateway:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): state.append('gateway-closed')
    class Adapter:
        def __init__(self, *a): pass
        def run(self, *a, **kw): return dict(status=status)
    def stop(identity):
        state.append('stopped')
        return dict(stopped=True)
    def audit(folder):
        assert state == ['stopped']
        return dict(passed=False, session_end=False, native_team_configs=0, teammate_idle_events=0)
    monkeypatch.setattr(krama, 'CredentialGateway', Gateway)
    monkeypatch.setattr(krama, 'ClaudeCodeSingleAgentCLI', Adapter)
    monkeypatch.setattr(krama, 'ClaudeCodeSubagentsCLI', Adapter)
    monkeypatch.setattr(krama, 'container', lambda *a, **kw: 'fixture')
    monkeypatch.setattr(krama, 'stop_container', stop)
    monkeypatch.setattr(krama, 'native_single_agent', audit)
    monkeypatch.setattr(krama, 'native_subagents', audit)
    monkeypatch.setattr(krama.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=0))
    args = SimpleNamespace(output=tmp_path, upstream=tmp_path, image='fixture', timeout=1)
    stopped = threading.Event()
    result = krama.run_attempt(Task('fixture', 'astronomy', 'public'), backend, args,
                              'synthetic', stopped, set(), threading.Lock())
    assert result['status'] == ('native_condition_unverified' if status == 'cli_exited' else status)
    assert state == ['stopped', 'gateway-closed']
    assert not stopped.is_set()


def test_free_readiness_retries_are_bounded_and_recorded(monkeypatch):
    calls = []
    def ready(timeout):
        calls.append(timeout)
        if len(calls) < 3:
            raise TimeoutError('synthetic TLS')
        return dict(tls_verified=True, model_calls=0)
    monkeypatch.setattr(web_fetch, 'check_ready', ready)
    result = web_fetch.check_ready_with_recovery(delay=0)
    assert calls == [10, 10, 10] and result['readiness_attempts'] == 3
    assert result['transient_failures'] == ['TimeoutError', 'TimeoutError']
    calls.clear()
    with pytest.raises(TimeoutError):
        web_fetch.check_ready_with_recovery(attempts=2, delay=0)
    assert len(calls) == 2


def test_sql_cap_is_opt_in_and_failure_is_actionable(tmp_path):
    path = tmp_path / 'fixture.sqlite'
    sqlite3.connect(path).close()
    query = 'WITH RECURSIVE t(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM t WHERE n<600000) SELECT sum(n) FROM t'
    assert run_sql(path, query)['rows'] == [(600000 * 600001 // 2,)]
    with pytest.raises(sqlite3.OperationalError, match='operation limit.*increase --operations'):
        run_sql(path, query, operations=1000)


@pytest.mark.parametrize('text,valid', [('```json\n{"equivalent":true}\n```', True),
    ('```\n{"equivalent":false}\n```', True), ('[true]', False),
    ('text {"equivalent":true}', False), ('```json\n{"equivalent":"true"}\n```', False)])
def test_judge_accepts_only_complete_json_or_complete_fenced_json(tmp_path, monkeypatch, text, valid):
    from benchmarks.kramabench import semantic_judge
    from test_semantic_judge_native import fake_grade
    monkeypatch.setattr(semantic_judge, 'grade_answer', fake_grade)
    calls = []
    def call(body):
        calls.append(body)
        return dict(content=[dict(type='text', text=text)])
    result = semantic_judge.judge_once(upstream=tmp_path, task_id='fixture', backend='claude-code-single-agent',
        submission_path=tmp_path/'submission.json', question='fixture', key='synthetic', output=tmp_path/'judge', call=call)
    assert (result['status'] == 'graded') is valid
    assert len(calls) == result['attempted_calls'] == 1


def test_explicit_longest_first_preserves_condition_pairs_and_default_order(tmp_path):
    from scripts.studies.benchmark_matrix import order_jobs
    jobs = [('kramabench', SimpleNamespace(id=t), c, tmp_path) for t in ('short', 'long')
            for c in ('single', 'native', 'structured')]
    assert order_jobs(jobs) == jobs
    path = tmp_path / 'times.json'
    path.write_text(json.dumps([dict(benchmark='kramabench', task_id=t, seconds=s)
                               for t, s in [('short', 10), ('long', 100)]]))
    assert [(t.id, c) for _, t, c, _ in order_jobs(jobs, path)] == [
        (t, c) for t in ('long', 'short') for c in ('single', 'native', 'structured')]
    path.write_text(json.dumps([dict(benchmark='kramabench', task_id='short', seconds=10)]))
    with pytest.raises(ValueError, match='exactly'):
        order_jobs(jobs, path)


def test_deferred_evaluation_is_offline_bound_and_idempotent(tmp_path, monkeypatch):
    from common.io import fingerprint, write_json
    from scripts.kramabench import run
    plan = dict(deferred_offline_evaluation=True, judge_limit=0, source={'fixture': 'hash'},
        image_id='image', cpu_per_attempt=8, compute_threads=4, replay_timeout_seconds=180,
        inputs_sha256=fingerprint({'data': 'hash'}), tasks=[dict(id='fixture')])
    report = dict(task_id='fixture', backend='claude-code-subagents', status='cli_exited',
                  container_id='owned', cleanup=dict(stopped=True))
    write_json(tmp_path/'summary.json', dict(plan=plan, rows=[report], offline_evaluation_pending=True))
    monkeypatch.setattr(run.shared, 'source_manifest', lambda: {'fixture': 'hash'})
    monkeypatch.setattr(run.runtime, 'input_inventory', lambda args: {'data': 'hash'})
    monkeypatch.setattr(run.shared, 'credential', lambda *a: pytest.fail('Offline evaluation read a credential'))
    monkeypatch.setattr(run.runtime, 'run_attempt', lambda *a: pytest.fail('Offline evaluation launched a solver'))
    calls = []
    def collect(folder, report, args):
        calls.append((args.cpus, args.compute_threads, args.replay_timeout))
        return dict(report, grade=dict(status='graded', score=1))
    monkeypatch.setattr(run.runtime, 'collect_attempt', collect)
    with pytest.raises(ValueError, match='source/image'):
        run.finalize_deferred(tmp_path, tmp_path/'upstream', 'wrong-image')
    run.finalize_deferred(tmp_path, tmp_path/'upstream', 'image')
    run.finalize_deferred(tmp_path, tmp_path/'upstream', 'image')
    assert calls == [(8, 4, 180)]
    assert not json.loads((tmp_path/'summary.json').read_text())['offline_evaluation_pending']


def test_timeout_submission_is_retained_but_not_a_success_or_pending_judge(tmp_path, monkeypatch):
    from scripts.kramabench import cli_runtime as krama
    work = tmp_path/'workspace'
    work.mkdir()
    (work/'submission.json').write_text(json.dumps(dict(answer='candidate', pipeline_path=None,
                                                      evidence='', unfinished=[])))
    monkeypatch.setattr(krama.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=0, stdout='{}'))
    monkeypatch.setattr(krama, 'grade_answer', lambda *a: dict(status='pending_judge', score=None))
    result = krama.collect_attempt(tmp_path, dict(task_id='fixture', backend='claude-code-subagents',
        status='timed_out', cli=dict(status='timed_out')), SimpleNamespace(upstream=tmp_path))
    assert result['status'] == 'timed_out'
    assert result['grade']['score'] == 0 and result['grade']['status'] == 'incomplete_timeout'
    assert result['artifact_grade']['status'] == 'pending_judge'
    assert (tmp_path/'submission.json').exists()
