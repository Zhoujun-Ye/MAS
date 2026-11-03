import hashlib
import json

import pytest

from benchmarks.kramabench.evaluation import NUMERIC_POLICY, UPSTREAM_NUMERIC_POLICY, numeric_success
from scripts.kramabench import rescore_native


def test_reuses_only_artifact_bound_semantic_verdicts():
    base = dict(answer_type='string_approximate', submission_file_sha256='same', target='reference',
                prediction='candidate', status='pending_judge', score=None, scoring_contract=dict(version='v3'))
    effective = dict(base, status='graded', score=1)
    result, reused = rescore_native.corrected_effective(dict(effective_grade=effective), base)
    assert reused and result['score'] == 1 and result['semantic_verdict_reused']
    with pytest.raises(ValueError, match='not bound'):
        rescore_native.corrected_effective(dict(effective_grade=dict(effective, submission_file_sha256='changed')), base)


def test_overlay_is_offline_versioned_and_does_not_modify_original(tmp_path, monkeypatch):
    original, overlay = tmp_path / 'run', tmp_path / 'overlay'
    folder = original / 'astronomy-hard-11/claude-code'
    folder.mkdir(parents=True)
    payload = b'{"answer":5.107269247909184e-13}'
    (folder / 'submission.json').write_bytes(payload)
    sha = hashlib.sha256(payload).hexdigest()
    def grade(upstream, task, submission, *, numeric_policy):
        score = int(numeric_policy == UPSTREAM_NUMERIC_POLICY)
        return dict(task_id=task, status='graded', answer_type='numeric_exact', metric='success',
            score_kind='binary', score=score, metrics=dict(success=score), prediction=5.107269247909184e-13,
            target=4.638e-13, submission_file_sha256=sha,
            scoring_contract=dict(version='pinned_answer_metrics_v2' if score else 'scale_aware_answer_metrics_v3'))
    old = grade(None, 'astronomy-hard-11', None, numeric_policy=UPSTREAM_NUMERIC_POLICY)
    source = json.dumps(dict(plan=dict(attempts=1), rows=[dict(task_id='astronomy-hard-11',
        backend='claude-code', grade=old)], paid_judge_calls=0)).encode()
    (original / 'summary.json').write_bytes(source)
    (original / 'progress.json').write_text('{"stage":"finished"}')
    monkeypatch.setattr(rescore_native, 'grade_answer', grade)
    monkeypatch.setattr(rescore_native, 'scoring_contract', lambda *a, **kw: dict(version=NUMERIC_POLICY))
    result = rescore_native.rescore(tmp_path / 'upstream', [original], overlay)
    assert result['changed'] == 1 and result['new_judge_calls'] == 0
    assert result['rows'][0]['original_grade']['score'] == 1
    assert result['rows'][0]['corrected_grade']['score'] == 0
    assert (original / 'summary.json').read_bytes() == source
    assert (folder / 'submission.json').read_bytes() == payload
    with pytest.raises(FileExistsError):
        rescore_native.rescore(tmp_path / 'upstream', [original], overlay)
    with pytest.raises(ValueError, match='Duplicate'):
        rescore_native.rescore(tmp_path / 'upstream', [original, original], tmp_path / 'duplicate')


def test_zero_and_numeric_string_routes_are_not_absolute_epsilon_loopholes():
    assert numeric_success(0, 0) == 1
    assert numeric_success('0.0', 0) == 1
    assert numeric_success('-0.0000001', 0) == 0
    assert numeric_success('5.107269247909184e-13', '4.638e-13') == 0
    assert numeric_success(10001.0, 10000.0) == 1
    assert numeric_success(10001.01, 10000.0) == 0
