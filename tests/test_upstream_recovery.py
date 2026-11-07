import json
from types import SimpleNamespace

import pytest

from scripts.studies.benchmark_matrix import upstream_recovery
from scripts.studies.matched_matrix_report import replace_upstream_failures


def original(tmp_path, status='cli_error', http_status=503, outcome='upstream_rejected'):
    root = tmp_path / 'original'
    run = root / 'solvers/kramabench/task/full'
    folder = run / 'task/claude-code-subagents'
    folder.mkdir(parents=True)
    (folder/'report.json').write_text(json.dumps(dict(status=status, cli=dict(returncode=1))))
    (folder/'gateway-requests.jsonl').write_text(json.dumps(dict(event='finished', upstream_attempted=True,
        route='/anthropic/v1/messages', http_status=http_status, outcome=outcome))+'\n')
    summary = dict(interrupted=False, authorization=dict(protocol_settings={}, task_manifest_sha256='manifest'),
        rows=[dict(benchmark='kramabench', task_id='task', backend='full', status=status, run=str(run))])
    (root/'summary.json').write_text(json.dumps(summary))
    jobs = [('kramabench', SimpleNamespace(id='task'), 'full', tmp_path/'new')]
    return root, jobs, folder, summary


@pytest.mark.parametrize('status', [500, 502, 503, 504])
def test_only_upstream_5xx_terminations_are_eligible(tmp_path, status):
    root, jobs, folder, _ = original(tmp_path, http_status=status)
    before = (root/'summary.json').read_bytes()
    result = upstream_recovery(root, jobs, {}, 'manifest')
    row, = result.values()
    assert row['http_status'] == status and row['backend'] == 'full'
    assert len(row['ledger_sha256']) == len(row['report_sha256']) == 64
    assert (root/'summary.json').read_bytes() == before


@pytest.mark.parametrize('status,http,outcome', [('cli_exited',503,'upstream_rejected'),
    ('native_condition_unverified',503,'upstream_rejected'), ('cli_error',429,'upstream_rejected'),
    ('cli_error',503,'rejected'), ('cli_error',400,'upstream_rejected')])
def test_wrong_answers_lifecycle_and_non_upstream_errors_are_not_recovered(tmp_path, status, http, outcome):
    root, jobs, _, _ = original(tmp_path, status=status, http_status=http, outcome=outcome)
    assert upstream_recovery(root, jobs, {}, 'manifest') == {}


@pytest.mark.parametrize('change', ['interrupted','settings','manifest','already_recovered','claimed','scope'])
def test_recovery_rejects_changed_or_repeated_scope(tmp_path, change):
    root, jobs, _, summary = original(tmp_path)
    if change == 'interrupted': summary['interrupted'] = True
    elif change == 'settings': summary['authorization']['protocol_settings'] = {'different': True}
    elif change == 'manifest': summary['authorization']['task_manifest_sha256'] = 'different'
    elif change == 'already_recovered': summary['authorization']['upstream_recovery_from'] = 'earlier'
    elif change == 'claimed': (tmp_path/'original.upstream-recovery-claim.json').write_text('{}')
    elif change == 'scope': jobs = []
    (root/'summary.json').write_text(json.dumps(summary))
    with pytest.raises(ValueError):
        upstream_recovery(root, jobs, {}, 'manifest')


def report_fixture():
    row = dict(benchmark='kramabench', task_id='task', backend='full', status='cli_error',
        score=1, raw_score=1, compliant_score=1, seconds=10, total_usd_offpeak=None,
        model_requests=2, native_audit_passed=False)
    auth = dict(protocol_settings={}, task_manifest_sha256='manifest')
    original = dict(run='first', authorization=auth, account_delta={'CNY':'1.20'}, rows=[row], limitations=[])
    recovery_row = dict(row, status='cli_exited', score=0, raw_score=0, compliant_score=0,
                        seconds=20, total_usd_offpeak=.2, native_audit_passed=True)
    recovery = dict(run='recovery', authorization=dict(auth, upstream_recovery_from='/outputs/first',
        upstream_recovery=[dict(benchmark='kramabench', task_id='task', backend='full')]),
        account_delta={'CNY':'2.30'}, rows=[recovery_row])
    return original, recovery


def test_recovery_replaces_even_a_better_old_score_without_hiding_costs():
    original, recovery = report_fixture()
    revised = replace_upstream_failures(original, recovery)
    assert revised['rows'][0]['score'] == 0
    assert revised['groups'][0]['attempts'] == 1
    assert revised['groups'][0]['mean_minutes'] == 20/60
    assert revised['account_delta'] == {'CNY':'3.50'}
    audit = revised['upstream_replacement']
    assert audit['total_attempts'] == 2 and audit['original_rows'][0]['score'] == 1
    assert audit['incurred_by_condition'][0]['total_usd_offpeak'] is None
    assert audit['incurred_by_condition'][0]['total_cli_seconds'] == 30
    assert original['rows'][0]['score'] == 1 and 'upstream_replacement' not in original


@pytest.mark.parametrize('change', ['wrong_task','duplicate','not_infrastructure','wrong_source','wrong_settings','repeat'])
def test_report_replacement_rejects_unbound_or_repeated_rows(change):
    original, recovery = report_fixture()
    if change == 'wrong_task': recovery['rows'][0]['task_id'] = 'different'
    elif change == 'duplicate': recovery['rows'].append(dict(recovery['rows'][0]))
    elif change == 'not_infrastructure': original['rows'][0]['status'] = 'cli_exited'
    elif change == 'wrong_source': recovery['authorization']['upstream_recovery_from'] = '/outputs/other'
    elif change == 'wrong_settings': recovery['authorization']['protocol_settings'] = {'different':True}
    elif change == 'repeat': original['upstream_replacement'] = {'previous':True}
    with pytest.raises(ValueError):
        replace_upstream_failures(original, recovery)
