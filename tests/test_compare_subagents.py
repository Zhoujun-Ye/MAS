import hashlib
import json

import pytest

from scripts.studies.compare_subagents import compare
from scripts.kramabench.results import summarize


def fixture(tmp_path):
    root = tmp_path/'subagents'
    folder = root/'a-easy-1/claude-code-subagents'
    folder.mkdir(parents=True)
    payload = b'{"answer":1}'
    (folder/'submission.json').write_bytes(payload)
    native = dict(rows=[dict(task_id='a-easy-1', backend='claude-code-subagents',
        status='cli_exited', grade=dict(answer_type='numeric_exact', score_kind='binary',
            metric='success', score=1, submission_file_sha256=hashlib.sha256(payload).hexdigest()))])
    scoring = dict(version='scale_aware_answer_metrics_v3')
    native['plan'] = dict(scoring=scoring)
    native['rows'][0]['subagents_audit'] = dict(passed=True, subagent_starts=1,
        native_team_configs=0, teammate_idle_events=0)
    (root/'summary.json').write_text(json.dumps(native))
    (root/'progress.json').write_text(json.dumps(dict(stage='finished')))
    rows = [dict(native['rows'][0], backend=b) for b in ('deepagents','claude-code-agent-team')]
    baseline = tmp_path/'baseline.json'
    baseline.write_text(json.dumps(dict(scoring=scoring, rows=rows,
        cohorts=dict(single=summarize(rows[:1]), team=summarize(rows[1:])))))
    return baseline, root


def test_comparison_is_read_only_and_reports_actual_delegation(tmp_path):
    baseline, root = fixture(tmp_path)
    original = (root/'summary.json').read_bytes()
    value = compare(baseline, root, tmp_path/'comparison', expected_tasks=1)
    assert value['cohorts']['subagents']['native_subagents_used_cases'] == 1
    assert value['new_solver_calls'] == value['new_judge_calls'] == 0
    assert len(value['rows']) == 3
    assert (root/'summary.json').read_bytes() == original


@pytest.mark.parametrize('violation', ['unfinished', 'artifact', 'team', 'scoring', 'duplicates'])
def test_invalid_comparisons_are_rejected(tmp_path, violation):
    baseline, root = fixture(tmp_path)
    native = json.loads((root/'summary.json').read_text())
    if violation == 'unfinished':
        (root/'progress.json').write_text('{"stage":"running"}')
    elif violation == 'artifact':
        (root/'a-easy-1/claude-code-subagents/submission.json').write_text('{}')
    elif violation == 'team':
        native['rows'][0]['subagents_audit']['native_team_configs'] = 1
    elif violation == 'scoring':
        native['plan']['scoring'] = {}
    else:
        native['rows'] *= 2
    (root/'summary.json').write_text(json.dumps(native))
    with pytest.raises(ValueError):
        compare(baseline, root, tmp_path/'comparison', expected_tasks=1)
    assert not (tmp_path/'comparison').exists()
