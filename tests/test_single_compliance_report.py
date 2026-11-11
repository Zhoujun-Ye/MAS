"""Derived compliance must not turn confirmed delegated work into valid Single credit."""

import copy
import csv
import json
import subprocess
import sys

import pytest

from scripts.studies import matched_matrix_report as reports


def fixture(root, *, status='single_agent_condition_violated', raw_score=1, record=None,
            backend='claude-code-single-agent'):
    run = root/'attempt'
    folder = run/'synthetic'/backend
    folder.mkdir(parents=True)
    report = dict(dict(status=status, single_agent_audit=dict(passed=False)), **(record or {}))
    (folder/'report.json').write_text(json.dumps(report))
    (run/'summary.json').write_text(json.dumps(dict(rows=[report])))
    (root/'summary.json').write_text(json.dumps(dict(
        authorization=dict(effort='none', solver_concurrency=1, judge_concurrency=1),
        rows=[dict(benchmark='kramabench', task_id='synthetic', backend=backend,
                   status='cli_exited', run=str(run))],
        grades=[dict(benchmark='kramabench', task_id='synthetic', backend=backend,
                     status='graded', grade=dict(status='graded', score=raw_score), judge_calls=0)])))
    return folder


@pytest.mark.parametrize('score', [0, 0.4, 1, None])
def test_confirmed_violation_preserves_raw_grade_but_has_zero_compliant_credit(tmp_path, score):
    fixture(tmp_path, raw_score=score)
    before = {p: p.read_bytes() for p in tmp_path.rglob('*.json')}
    result = reports.collect(tmp_path)
    row = result['rows'][0]
    assert row['score'] == row['raw_score'] == score
    assert row['compliant_score'] == 0 and row['protocol_accepted'] is False
    assert row['condition_status'] == 'single_agent_condition_violated'
    assert result['groups'][0]['attempts'] == 1
    assert result['groups'][0]['compliant_accuracy'] == 0
    assert result['groups'][0]['raw_accuracy'] == score
    assert all(p.read_bytes() == contents for p, contents in before.items())


@pytest.mark.parametrize('source', ['condition', 'audit', 'accounting', 'late-summary'])
def test_violation_evidence_is_not_lost_when_matrix_lifecycle_status_is_stale(tmp_path, source):
    record = {}
    if source == 'condition':
        record['condition_status'] = 'single_agent_condition_violated'
    elif source == 'audit':
        record['single_agent_audit'] = dict(passed=False, subagent_starts=1)
    elif source == 'accounting':
        record['accounting'] = dict(by_role=dict(member=dict(observed_messages=1)))
    folder = fixture(tmp_path, status='native_condition_unverified', record=record)
    if source == 'late-summary':
        (folder.parent.parent/'summary.json').write_text(json.dumps(dict(rows=[dict(
            status='single_agent_condition_violated', single_agent_audit=dict(passed=False))])))
    assert reports.collect(tmp_path)['rows'][0]['compliant_score'] == 0


@pytest.mark.parametrize('backend', ['claude-code-single-agent', 'claude-code-subagents'])
def test_missing_end_alone_does_not_imply_a_confirmed_single_violation(tmp_path, backend):
    fixture(tmp_path, status='native_condition_unverified', backend=backend,
            record=dict(single_agent_audit=dict(passed=False, session_end=False)))
    row = reports.collect(tmp_path)['rows'][0]
    assert row['score'] == row['compliant_score'] == 1
    assert row['protocol_accepted'] is None
    assert 'condition_status' not in row


def test_summary_cannot_erase_positive_violation_evidence_from_attempt(tmp_path):
    folder = fixture(tmp_path, status='native_condition_unverified',
        record=dict(single_agent_audit=dict(passed=False, subagent_starts=1)))
    (folder.parent.parent/'summary.json').write_text(json.dumps(dict(rows=[dict(
        status='cli_exited', single_agent_audit=dict(passed=True, subagent_starts=0))])))
    assert reports.collect(tmp_path)['rows'][0]['compliant_score'] == 0


def test_derived_json_csv_markdown_and_from_report_agree(tmp_path):
    fixture(tmp_path)
    result = reports.collect(tmp_path)
    # Reproduce an older export that mislabeled a known violation.
    old = copy.deepcopy(result)
    old['rows'][0].update(compliant_score=1, protocol_accepted=None)
    old['groups'] = reports.summarize(old['rows'])
    unchanged = copy.deepcopy(old)
    reports.write_report(old, tmp_path/'direct')
    assert old == unchanged
    rendered = json.loads((tmp_path/'direct/summary.json').read_text())
    assert rendered['rows'][0]['compliant_score'] == 0
    with (tmp_path/'direct/task-results.csv').open() as stream:
        row = next(csv.DictReader(stream))
    assert row['raw_score'] == '1' and row['compliant_score'] == '0'
    assert 'Raw Mean | Compliant Mean' in (tmp_path/'direct/REPORT.md').read_text()
    source = tmp_path/'old.json'
    source.write_text(json.dumps(old))
    run = subprocess.run([sys.executable, '-m', 'scripts.studies.matched_matrix_report',
        '--from-report', str(source), '--output', str(tmp_path/'new.json'),
        '--report-dir', str(tmp_path/'via-cli')], capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stderr
    new = json.loads((tmp_path/'new.json').read_text())
    assert new['groups'][0]['compliant_accuracy'] == 0
    assert json.loads(source.read_text()) == old


def test_costs_legacy_decision_results_and_unknowns_remain_unchanged(tmp_path):
    fixture(tmp_path, status='native_condition_unverified')
    result = reports.collect(tmp_path)
    row = result['rows'][0]
    row.update(raw_score=None, score=None, compliant_score=None,
               total_usd_offpeak=None, known_model_usd_offpeak_subtotal=.2,
               protocol_accepted=None)
    legacy = dict(row, backend='full', compliant_score=0, protocol_accepted=False)
    result['rows'].append(legacy)
    new = reports.normalize_compliance(result)
    assert new['rows'] == result['rows']
    assert reports.normalize_compliance(new) == new


def test_direct_aggregation_cannot_reuse_stale_compliant_credit(tmp_path):
    fixture(tmp_path)
    row = reports.collect(tmp_path)['rows'][0]
    row['compliant_score'] = 1
    group = reports.summarize([row])[0]
    assert group['raw_accuracy'] == 1
    assert group['compliant_accuracy'] == 0
