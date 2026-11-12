"""Read-only accounting for retained historical loop-intervention evidence."""

import copy
import json

from analysis.native_evidence import loop_guard_evidence
from scripts.studies import matched_matrix_report as reports


def row(task='task', backend='native', score=1, status='cli_exited', *, measured=True, warning=0, stop=0):
    roles = dict(lead=dict(warnings=0, stops=0), worker=dict(warnings=warning, stops=stop))
    return dict(benchmark='kramabench', task_id=task, backend=backend, score=score, status=status,
                seconds=60, total_usd_offpeak=.1, model_requests=10, native_audit_passed=True,
                loop_guard=dict(measured=measured, by_role=roles, triggered=bool(warning or stop) if measured else None))


def test_guard_error_is_excluded_but_costs_raw_scores_and_model_failures_remain():
    rows = [row('success'), row('bad-guard', score=None, status='loop_guard_error'),
            row('timeout', score=0, status='timed_out'), row('lead-loop', score=0, status='loop_detected'),
            row('worker-loop', score=1, warning=1, stop=1)]
    group = reports.summarize(rows)[0]
    assert group['attempts'] == 5 and group['primary_denominator'] == 4
    assert group['excluded_harness_errors'] == 1 and group['primary_accuracy'] == .5
    assert group['raw_accuracy'] is None
    assert group['total_usd_offpeak'] == .5 and group['model_requests'] == 50
    assert group['loop_counts']['warnings']['worker'] == group['loop_counts']['stops']['worker'] == 1


def test_unknown_guard_evidence_is_not_zero_or_a_clean_sensitivity_sample():
    rows = [row(measured=False)]
    group = reports.summarize(rows)[0]
    assert group['loop_counts'] is None and group['loop_observed_attempts'] == 0
    assert reports.loop_sensitivity(rows)['status'] == 'unavailable'


def test_sensitivity_removes_matching_task_from_every_condition_including_untouched_single():
    rows = [row(task=t, backend=b) for t in ['clean', 'worker-loop', 'bad-guard']
            for b in ['claude-code-single-agent', 'native', 'claude-code-subagents']]
    rows[4] = row('worker-loop', 'native', warning=1, stop=1)
    rows[8] = row('bad-guard', 'claude-code-subagents', score=None, status='loop_guard_error')
    before = copy.deepcopy(rows)
    sensitivity = reports.loop_sensitivity(rows)
    assert rows == before and sensitivity['excluded_attempts'] == 6
    assert sensitivity['excluded_tasks'] == [dict(benchmark='kramabench', task_id=t) for t in ['bad-guard', 'worker-loop']]
    assert all(g['primary_denominator'] == 1 for g in sensitivity['groups'])


def test_known_harness_error_can_be_excluded_even_if_its_hook_log_is_missing():
    rows = [row('clean'), row('bad', measured=False, score=None, status='loop_guard_error'),
            row('bad', backend='claude-code-single-agent', measured=False)]
    result = reports.loop_sensitivity(rows)
    assert result['status'] == 'available' and result['excluded_attempts'] == 2
    assert all(g['primary_denominator'] == 1 for g in result['groups'])


def test_primary_metrics_drop_a_guard_error_task_from_all_conditions_without_erasing_costs():
    rows = [row(t,b,score=1 if t=='bad' else .5) for t in ['clean','bad']
            for b in ['claude-code-single-agent','native','claude-code-subagents']]
    rows[4].update(status='loop_guard_error',score=None)
    result = reports.normalize_compliance(dict(rows=rows))
    for g in result['groups']:
        assert g['primary_denominator'] == 1 and g['primary_accuracy'] == .5
        assert g['paired_harness_excluded_attempts'] == 1
        assert g['total_usd_offpeak'] == .2
    bad = [r for r in result['rows'] if r['task_id']=='bad']
    assert all(not r['primary_score_eligible'] for r in bad)
    assert sum(r.get('harness_error')=='loop_guard_error' for r in bad)==1
    assert all(r['score']==1 for r in bad if r['backend']!='native')


def test_no_tool_session_is_measured_zero_not_unknown(tmp_path):
    path=tmp_path/'native-profile/observer/events.jsonl';path.parent.mkdir(parents=True)
    path.write_text(json.dumps(dict(hook_event_name='SessionStart',session_id='session',
        loop_detection=dict(status='policy_active',actor_role='lead',policy=dict(version=3))))+'\n')
    evidence=loop_guard_evidence(tmp_path)
    assert evidence['measured'] and evidence['triggered'] is False
    assert all(v==0 for role in evidence['by_role'].values() for v in role.values())
    item=row();item['loop_guard']=evidence
    assert reports.loop_sensitivity([item])['status']=='available'


def test_reader_counts_roles_deduplicates_and_never_reconstructs_legacy_hits(tmp_path):
    path = tmp_path/'native-profile/observer/events.jsonl'; path.parent.mkdir(parents=True)
    legacy = dict(hook_event_name='PostToolUse', tool_use_id='old', session_id='session', tool_response='same')
    path.write_text(json.dumps(legacy)+'\n')
    assert loop_guard_evidence(tmp_path)['triggered'] is None
    events = [dict(legacy, tool_use_id='warning', agent_id='worker', loop_detection=dict(
        status='warning', actor_role='worker', policy=dict(version=2))),
        dict(legacy, tool_use_id='stop', agent_id='worker', loop_detection=dict(
            status='loop_detected', actor_role='worker', scope='worker', policy=dict(version=2))),
        dict(legacy, tool_use_id='error', loop_detection=dict(status='loop_guard_error',
            actor_role='lead', policy=dict(version=2)))]
    path.write_text(''.join(json.dumps(e)+'\n' for e in events+events))
    result = loop_guard_evidence(tmp_path)
    assert result['measured'] and result['triggered'] and result['policy_versions'] == [2]
    assert result['by_role']['worker']['warnings'] == result['by_role']['worker']['stops'] == 1
    assert result['by_role']['lead']['errors'] == 1
    with path.open('a') as stream: stream.write('broken\n')
    result = loop_guard_evidence(tmp_path)
    assert not result['measured'] and result['invalid_events'] == 1 and result['triggered'] is None


def test_exports_keep_primary_exclusions_and_role_counts_consistent(tmp_path):
    report = dict(run='fixture', authorization=dict(effort='none', solver_concurrency=2, judge_concurrency=1),
        rows=[row('success', warning=1, stop=1), row('error', score=None, status='loop_guard_error')], limitations=[])
    before = copy.deepcopy(report)
    reports.write_report(report, tmp_path/'report')
    assert report == before
    result = json.loads((tmp_path/'report/summary.json').read_text())
    assert result['rows'][0]['primary_score_eligible'] and not result['rows'][1]['primary_score_eligible']
    assert result['rows'][0]['loop_worker_stops'] == 1
    assert result['groups'][0]['primary_accuracy'] == 1
    assert result['groups'][0]['primary_denominator'] == 1
    assert reports.normalize_compliance(result) == result
    assert 'loop_worker_stops' in (tmp_path/'report/task-results.csv').read_text()
    text = (tmp_path/'report/REPORT.md').read_text()
    assert 'Primary N' in text and 'Worker Stops' in text and 'Paired Loop Sensitivity' in text
