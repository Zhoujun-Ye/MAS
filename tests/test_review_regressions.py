import json
from pathlib import Path
import subprocess
import sys

import pytest

from fakes import ScriptedClient
from test_agent_team import build
from harness.agent import Observation
from harness.execution import ContainerWorkspace
from harness.trace import read_trace
from analysis.information import decision_case
from benchmarks.cooperbench.snapshot import capture, implementation_path


@pytest.mark.parametrize('scheduler', ['controlled', 'async'])
def test_deferred_final_recovers_when_worker_only_waits(tmp_path, scheduler):
    def policy(messages, tools, choice):
        role = messages[0]['content'].split('Member identity: ')[1].split('.')[0]
        count = sum(m['role'] == 'assistant' for m in messages)
        if role == 'leader':
            if count == 0:
                return dict(calls=[('send_message', dict(recipient='researcher', content='Check status'))])
            return dict(content='Final')
        if count == 0:
            return dict(calls=[('submit_assignment', dict(report='Ready'))])
        if role == 'researcher' and count == 1:
            return dict(calls=[('list_tasks', {})])
        return dict(calls=[('wait_for_message', {})])
    task, team, trace = build(tmp_path, 'agent_team', ScriptedClient(policy), scheduler=scheduler)
    result = team.run_task(task)
    assert result['submission_status'] == 'submitted' and result['failure_class'] is None
    if scheduler == 'controlled':
        assert team.calls_by_member['leader'] == 3
    trace.close()


@pytest.mark.parametrize('text', ['', 'I will inspect the tests', 'Done'])
@pytest.mark.parametrize('scheduler', ['controlled', 'async'])
def test_tool_free_worker_is_idle_not_submission_or_message(tmp_path, text, scheduler):
    task, team, trace = build(tmp_path, 'agent_team', ScriptedClient(lambda *a: dict(content=text)), scheduler=scheduler)
    result = team.run_task(task)
    assert result['status'] == 'incomplete' and result['failure_class'] == 'agent_failure'
    assert not team.submissions and team.sent == 0
    assert team.calls_by_member['leader'] == 1  # Startup turn, not idle polling.
    trace.close()


@pytest.mark.parametrize('scheduler', ['controlled', 'async'])
def test_one_member_cannot_spend_peer_model_tool_or_message_budgets(tmp_path, scheduler):
    def policy(messages, tools, choice):
        role = messages[0]['content'].split('Member identity: ')[1].split('.')[0]
        if role == 'researcher':
            return dict(calls=[('stock', {}), ('send_message', dict(recipient='leader', content='Update'))])
        if role == 'reviewer':
            return dict(calls=[('submit_assignment', dict(report='Ready'))])
        return dict(calls=[('wait_for_message', {})])
    task, team, trace = build(tmp_path, 'agent_team', ScriptedClient(policy), scheduler=scheduler,
                              member_limits={'researcher': dict(max_calls=2, tool_budget=1, max_messages=1)})
    result = team.run_task(task)
    assert result['failure_class'] == 'agent_failure'
    assert team.calls_by_member['researcher'] == 2 and team.calls_by_member['reviewer'] == 1
    assert team.budgets['researcher'].used == 1 and team.budgets['reviewer'].used == 0
    assert team.messages_by_member['researcher'] == 1 and team.messages_by_member['reviewer'] == 1
    assert team.submitted['reviewer'] and not team.submitted['researcher']
    trace.close()


@pytest.mark.parametrize('ending', ['idle', 'budget', 'context'])
def test_agent_failure_still_captures_terminal_artifacts(tmp_path, ending):
    captured = []
    def snapshot(role, revision, paths):
        captured.append((role, paths))
        return dict(patch='partial-' + role)
    def policy(*args):
        return dict(calls=[('list_tasks', {})]) if ending == 'budget' else dict(content='')
    task, team, trace = build(tmp_path, 'agent_team', ScriptedClient(policy), submission_hook=snapshot,
                              max_calls=2, max_input_chars=1 if ending == 'context' else 200_000)
    result = team.run_task(task)
    assert result['failure_class'] == 'agent_failure'
    assert set(result['evaluation_snapshots']) == {'researcher', 'reviewer'}
    assert all(row['kind'] == 'terminal' for row in result['evaluation_snapshots'].values())
    assert all(paths is None for _, paths in captured)
    assert not any(team.submitted.values())
    trace.close()


def test_code_and_messages_reach_model_as_exact_text(tmp_path, monkeypatch):
    code = 'return f"Hello, {name}!"  # \u4f60\u597d\nsecond = "\\n"\n'
    workspace = ContainerWorkspace('fixture')
    monkeypatch.setattr(workspace, 'execute', lambda *a: dict(output=code, exit_code=0, truncated=False))
    observation = workspace.tools()[1].run(dict(path='source.py'), None)
    assert observation.text.split('\n', 1)[1] == code
    task, team, trace = build(tmp_path, 'agent_team')
    team.domain['stock'].run = lambda *a: observation
    team.run_task(task)
    own = [m['content'] for m in team.agents['researcher'].messages if m['role'] == 'tool']
    assert any(text.endswith(code) for text in own)
    team.queue('researcher', 'reviewer', code, [])
    team.receive('reviewer')
    message = team.agents['reviewer'].messages[-1]['content']
    assert message.split('\n\n', 1)[1] == code
    assert all('incoming_handoff' not in str(a.messages) and 'handoff_form' not in str(a.messages)
               and 'context_id' not in str(a.messages) for a in team.agents.values())
    trace.close()


class LocalWorkspace:
    """Only fixed test commands, inside a temporary fixture repo on the server."""
    def __init__(self, root):
        self.root = root
    def execute(self, command):
        p = subprocess.run(command, shell=True, cwd=self.root, capture_output=True, text=True, timeout=10)
        return dict(output=p.stdout, exit_code=p.returncode, truncated=False)


def test_real_git_snapshot_selects_implementation_and_preserves_index(tmp_path):
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=tmp_path, text=True).strip()
    git('init', '-q')
    (tmp_path / 'source.py').write_text('value = 1\n')
    (tmp_path / 'test_source.py').write_text('assert True\n')
    git('add', '.')
    git('-c', 'user.name=Offline', '-c', 'user.email=offline@example.invalid', 'commit', '-qm', 'fixture')
    base = git('rev-parse', 'HEAD')
    (tmp_path / 'source.py').write_text('value = 2\n')
    (tmp_path / 'test_source.py').write_text('assert False\n')
    (tmp_path / 'repro.py').write_text('scratch\n')
    (tmp_path / 'new_impl.py').write_text('value = 3\n')
    git('add', 'repro.py')  # An accidental stage must not leak into the patch.
    index_before = git('diff', '--cached')
    workspace = LocalWorkspace(tmp_path)
    explicit = capture(workspace, base, ['source.py', 'new_impl.py'])
    assert explicit['selected_paths'] == ['new_impl.py', 'source.py']
    assert 'value = 2' in explicit['patch'] and 'value = 3' in explicit['patch']
    assert 'repro.py' not in explicit['patch'] and 'test_source.py' not in explicit['patch']
    assert git('diff', '--cached') == index_before
    terminal = capture(workspace, base)
    assert terminal == explicit
    with pytest.raises(ValueError):
        capture(workspace, base, ['test_source.py'])
    with pytest.raises(ValueError):
        capture(workspace, base, ['.'])
    (tmp_path / 'source.py').write_text('value = 99\n')
    assert '99' not in explicit['patch']


@pytest.mark.parametrize('path', ['../secret', '/tmp/file', '.git/config', 'tests/unit.py', 'x.test.ts',
                                  '.cooperbench_scratch/reproduce.py', 'test_thing.py', 'trace.log'])
def test_forbidden_submission_paths(path):
    assert not implementation_path(path)


def test_feedback_defaults_to_worker_steps_not_leader_final(tmp_path):
    from analysis.runs import load_runs
    from scripts.analyze import summarize
    task, team, trace = build(tmp_path, 'agent_team')
    result = team.run_task(task)
    trace.emit('run_end', status=result['status'])
    trace.close()
    events = read_trace(trace.path)
    assert decision_case(events)['decider'] != 'leader'
    trace.path.rename(tmp_path / 'trace.jsonl')
    (tmp_path / 'manifest.json').write_text(json.dumps(dict(scheduler='controlled', communication_policy={})))
    (tmp_path / 'result.json').write_text(json.dumps(result))
    report_dir = tmp_path.parent / (tmp_path.name + '-feedback')
    root = Path(__file__).resolve().parents[1]
    subprocess.run([sys.executable, str(root / 'scripts/feedback.py'), str(tmp_path), '--report-dir', str(report_dir)],
                   check=True, capture_output=True, text=True, timeout=15)
    rows = json.loads((report_dir / 'index.json').read_text())
    assert rows and all(r['agent'] != 'leader' for r in rows)
    assert len(rows) == sum(e['type'] == 'model_input' and e['agent'] != 'leader' for e in events)
    runs, _ = load_runs(tmp_path)
    assert next(iter(summarize(runs)['conditions'].values()))['runs'] == 1


def test_message_appended_but_not_consumed_at_member_cap_blocks_success(tmp_path):
    from harness.agent_team import MemberLimit
    task, team, trace = build(tmp_path, 'agent_team')
    team.run_task(task)
    team.calls_by_member['reviewer'] = team.member_limits['reviewer']['max_calls']
    team.queue('researcher', 'reviewer', 'Late correction', [])
    with pytest.raises(MemberLimit):
        team.prepare_call(team.agents['reviewer'])
    assert team.awaiting_input['reviewer'] and not team.inbox['reviewer']
    assert not team.ready_to_finalize()
    trace.close()


def test_cost_report_includes_failed_attempt_usage_and_account_scope():
    from harness.accounting import report
    pricing = dict(models={'fixture': dict(cache_hit=1, cache_miss=2, output=3)}, peak_hours_utc=[], peak_multiplier=1)
    events = [dict(type='llm_call', model='fixture', agent='worker_a', ts='2026-10-30T00:00:00+00:00',
                   usage=dict(prompt_tokens=100, cache_hit_tokens=40, cache_miss_tokens=60, completion_tokens=10)),
              dict(type='run_end', status='error')]
    before = dict(status='recorded', balances=[dict(currency='USD', total='10')])
    after = dict(status='recorded', balances=[dict(currency='USD', total='9.99')])
    costs = report(events, pricing, before, after)
    assert costs['cost_usd_estimate'] == pytest.approx(190 / 1_000_000)
    assert costs['account_balance_delta'] == {'USD': '0.01'}
    assert costs['usage']['total']['llm_calls'] == 1 and 'not attributable' in costs['balance_scope']
    unknown = report(events, pricing, dict(status='unavailable'), after)
    assert unknown['account_balance_delta'] == {} and unknown['cost_usd_estimate'] is not None


def test_analysis_separates_limits_and_keeps_contaminated_attempts(tmp_path):
    import hashlib
    from analysis.runs import load_runs
    from scripts.analyze import summarize
    audits = {}
    for i, cap in enumerate((None, 200000)):
        folder = tmp_path / str(i)
        folder.mkdir()
        raw = json.dumps(dict(type='run_start', t=i)) + '\n'
        (folder / 'trace.jsonl').write_text(raw)
        (folder / 'manifest.json').write_text(json.dumps(dict(scheduler='async', limits=dict(token_budget=cap))))
        (folder / 'result.json').write_text(json.dumps(dict(status='completed')))
        (folder / 'grade.json').write_text(json.dumps(dict(status='graded', correct=True)))
        audits[hashlib.sha256(raw.encode()).hexdigest()] = dict(status='contaminated')
    runs, _ = load_runs(tmp_path, audits)
    report = summarize(runs)
    assert len(report['conditions']) == 2
    for row in report['conditions'].values():
        assert row['runs'] == row['confirmed_successes'] == 1
        assert row['research_audit_counts']['contaminated'] == 1
        assert row['research_admissible_successes'] == 0


def test_runner_persists_accounting_on_provider_failure(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from scripts.cooperbench import run
    from harness.llm import ProviderError
    output = tmp_path / 'attempt'
    monkeypatch.setattr(sys, 'argv', ['run.py', '--repo', 'sample_task', '--task', '0', '--features', '1', '2',
                                     '--containers', 'a', 'b', '--output', str(output), '--authorized-one-paid-pair'])
    monkeypatch.setattr(run, 'verify_checkout', lambda: tmp_path)
    monkeypatch.setattr(run.Pair, 'private_inputs', lambda *a: {})
    def inspect(argv, **kwargs):
        if argv[:2] == ['docker', 'inspect']:
            return json.dumps([dict(Id=r, Image='image', Mounts=[], HostConfig=dict(NetworkMode='none')) for r in ('a', 'b')])
        return json.dumps([dict(Id='image')])
    monkeypatch.setattr(run.subprocess, 'check_output', inspect)
    class Workspace:
        def __init__(self, *a, **kw):
            pass
        def execute(self, command):
            return dict(exit_code=0, truncated=False, output='a' * 40 if command == 'git rev-parse HEAD' else '')
    monkeypatch.setattr(run, 'ContainerWorkspace', Workspace)
    monkeypatch.setattr(run, 'verify_worker', lambda w, b: dict(version='fixture'))
    monkeypatch.setattr(run, 'source_digest', lambda: 'fixture')
    monkeypatch.setattr(run, 'load_env', lambda: None)
    monkeypatch.setattr(run, 'load_config', lambda _: dict(agent_model=dict(model='scripted'), pricing=dict(
        models={'scripted': dict(cache_hit=1, cache_miss=2, output=3)}, peak_hours_utc=[], peak_multiplier=1)))
    closed = []
    monkeypatch.setattr(run, 'ChatClient', lambda cfg: SimpleNamespace(_http=SimpleNamespace(close=lambda: closed.append(True))))
    balances = iter(['10', '9'])
    monkeypatch.setattr(run, 'observed_balance', lambda cfg: dict(status='recorded', balances=[dict(currency='USD', total=next(balances))]))
    def make_team(pair, dataset, workspaces, client, trace, **kwargs):
        def fail(request):
            trace.emit('llm_call', agent='worker_a', model='scripted', usage=dict(prompt_tokens=100,
                       cache_hit_tokens=40, cache_miss_tokens=60, completion_tokens=10))
            raise ProviderError('transport', 'fixture')
        return SimpleNamespace(run_task=fail)
    monkeypatch.setattr(run, 'make_team', make_team)
    with pytest.raises(ProviderError):
        run.main()
    result = json.loads((output / 'result.json').read_text())
    costs = json.loads((output / 'accounting.json').read_text())
    assert result['failure_class'] == 'infrastructure_error' and result['error_kind'] == 'transport'
    assert costs['usage']['total']['llm_calls'] == 1 and costs['account_balance_delta'] == {'USD': '1'}
    assert closed == [True]
