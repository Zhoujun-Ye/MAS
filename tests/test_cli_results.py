import hashlib
import json

import pytest

from scripts.kramabench.results import linked_diagnostics, load_audit, publish, replace_tasks, summarize


def make_audit(root, backend, values):
    rows, corrected = [], []
    for task, prediction, score in values:
        folder = root / task / backend
        folder.mkdir(parents=True)
        payload = json.dumps(dict(answer=prediction)).encode()
        (folder / 'submission.json').write_bytes(payload)
        sha = hashlib.sha256(payload).hexdigest()
        grade = dict(answer_type='numeric_exact', score_kind='binary', metric='success', score=score,
                     prediction=prediction, target=1e-13, submission_file_sha256=sha,
                     scoring_contract=dict(version='scale_aware_answer_metrics_v3'))
        row = dict(task_id=task, backend=backend, status='cli_exited', grade=grade,
            cli=dict(elapsed_seconds=3), pipeline_exit_code=0, pipeline_answer_matches_submission=True,
            single_agent_audit=dict(passed=True, subagent_starts=0, executed_delegation_tools=0),
            single_agent_checkpoint_audit=dict(member_messages=0),
            accounting=dict(estimated_usd_off_peak=0.01, estimated_usd_peak=0.02,
                            observed_totals=dict(input_tokens=100, output_tokens=10, cache_hit_tokens=50)))
        rows.append(row)
        corrected.append(dict(task_id=task, backend=backend, corrected_grade=grade,
                              submission_file_sha256=sha, source_run=str(root)))
    payload = json.dumps(dict(rows=rows)).encode()
    (root / 'summary.json').write_bytes(payload)
    directory = root.parent / (root.name + '-audit')
    directory.mkdir()
    audit = directory / 'summary.json'
    audit.write_text(json.dumps(dict(scoring=dict(version='scale_aware_answer_metrics_v3'), rows=corrected,
        source_runs=[dict(root=str(root), summary_sha256=hashlib.sha256(payload).hexdigest())])))
    return audit


def test_replacements_are_unconditional_not_best_score_selection():
    old = dict(backend='claude-code', source_run='old', status='cli_exited',
               grade=dict(target=1, score=1, submission_file_sha256='old'))
    new = dict(old, source_run='new', grade=dict(target=1, score=0, submission_file_sha256='new'))
    merged = replace_tasks(dict(task=old), dict(task=new))
    assert merged['task']['grade']['score'] == 0
    assert merged['task']['replacement']['previous_score'] == 1
    assert old['grade']['score'] == 1
    with pytest.raises(ValueError, match='subset'):
        replace_tasks(dict(task=old), dict(other=new))


def test_publish_keeps_matched_workload_and_preserves_originals(tmp_path):
    single = make_audit(tmp_path/'single', 'deepagents', [('a-easy-1', 1e-13, 1), ('b-hard-1', 0, 0)])
    team = make_audit(tmp_path/'team', 'claude-code', [('a-easy-1', 1e-13, 1), ('b-hard-1', 0, 0)])
    repaired = make_audit(tmp_path/'repair', 'claude-code', [('b-hard-1', 1e-13, 1)])
    original = (tmp_path/'team/summary.json').read_bytes()
    result = publish(single, team, repaired, tmp_path/'publication', expected_tasks=2, expected_repairs=1)
    assert len(result['rows']) == 4
    assert result['cohorts']['team']['binary_correct'] == 2
    assert result['cohorts']['single']['binary_correct'] == 1
    assert result['cohorts']['team']['replay_pass'] == 2
    assert result['team_all_attempts_visible_cost']['attempts'] == 3
    assert result['new_judge_calls'] == result['new_solver_calls'] == 0
    assert (tmp_path/'team/summary.json').read_bytes() == original
    assert (tmp_path/'publication/replacements.json').is_file()
    with pytest.raises(FileExistsError):
        publish(single, team, repaired, tmp_path/'publication', expected_tasks=2, expected_repairs=1)


def test_audit_binds_original_summary_and_exact_artifacts(tmp_path):
    audit = make_audit(tmp_path/'raw', 'deepagents', [('a-easy-1', 1e-13, 1)])
    (tmp_path/'raw/a-easy-1/deepagents/submission.json').write_text('{"answer":0}')
    with pytest.raises(ValueError, match='artifact'):
        load_audit(audit, 'deepagents')


def test_missing_scores_and_accounting_are_unknown():
    row = dict(task_id='a-easy-1', status='cli_error', grade=dict(answer_type='string_approximate',
        metric='llm_paraphrase', score_kind='binary', score=None))
    stats = summarize([row])
    assert stats['binary_accuracy'] is None and stats['binary_scored'] == 0
    assert stats['selected_artifact_visible_cost']['estimated_usd_off_peak'] is None


def test_linked_diagnostic_expenditure_is_kept_and_bound(tmp_path):
    old, selected = tmp_path/'diagnostic', tmp_path/'selected'
    old.mkdir()
    selected.mkdir()
    payload = json.dumps(dict(rows=[dict(task_id='first', status='cli_error')])).encode()
    (old/'summary.json').write_bytes(payload)
    (selected/'summary.json').write_text(json.dumps(dict(plan=dict(continuation_from=str(old),
        previous_summary_sha256=hashlib.sha256(payload).hexdigest()))))
    rows = [dict(source_run=str(selected))]
    assert linked_diagnostics(rows)[0]['status'] == 'cli_error'
    (old/'summary.json').write_text('{"rows":[]}')
    with pytest.raises(ValueError, match='ledger changed'):
        linked_diagnostics(rows)
