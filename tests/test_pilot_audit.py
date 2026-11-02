import hashlib
import json

from scripts.kramabench.audit import artifact_errors
from scripts.kramabench.audit import checkpoint_audit


def test_artifact_audit_rejects_native_rewrite_and_wrong_binding():
    code = 'print(4)\n'
    submission = {'pipeline_code': code}
    binding = {'pipeline_code_sha256': hashlib.sha256(code.encode()).hexdigest()}
    assert artifact_errors(submission, {'code': code}, binding) == []
    assert len(artifact_errors(submission, {'code': 'print(5)'}, {})) == 2
    assert artifact_errors({}, {}, {}) == ['No exported pipeline code']


def test_checkpoint_audit_checks_pause_resume_cancel_and_submit_prefix():
    pause = dict(type='team_checkpoint', t=1, worker_id='w', cause='assignment', task_id='t')
    call = dict(type='llm_attempt', t=2, agent='w')
    result = checkpoint_audit([pause, call])
    assert result['violations'][0]['reason'] == 'model_call_while_checkpointed'
    resume = dict(type='team_checkpoint_resume', t=2, agent='w')
    result = checkpoint_audit([pause, resume, call, dict(type='tool_call', t=3, tool='submit', error=False)])
    assert result['count'] == result['resumed'] == 1 and not result['violations']
    assert result['first_valid_submit_model_call'] == 1 and result['submitted_within_128']
    cancel = dict(type='team_task', t=2, event='cancel', task=dict(owner='w', task_id='t'))
    assert not checkpoint_audit([pause, cancel, call])['violations']
    assert not checkpoint_audit([pause, dict(type='team_draining', t=2), call])['violations']


def test_checkpoint_audit_does_not_impute_success_at_128_calls():
    events = [dict(type='llm_attempt', t=i, agent='leader') for i in range(129)]
    events.append(dict(type='tool_call', t=130, tool='submit', error=True))
    assert checkpoint_audit(events)['first_valid_submit_model_call'] is None
    events.append(dict(type='tool_call', t=131, tool='submit', error=False))
    result = checkpoint_audit(events)
    assert result['first_valid_submit_model_call'] == 129 and not result['submitted_within_128']


def test_audit_keeps_binary_continuous_and_pending_scores_separate(tmp_path):
    from scripts.kramabench.audit import audit
    usage = {k: 1 for k in ('attempted_calls', 'failed_calls', 'prompt_tokens', 'completion_tokens',
                           'cache_hit_tokens', 'cache_miss_tokens', 'max_prompt_tokens')}
    grades = [dict(answer_type='numeric_exact', score=1, score_kind='binary', metrics={'success': 1}),
              dict(answer_type='numeric_approximate', score=1.0, score_kind='continuous', metrics={'rae_score': 1.0}),
              dict(answer_type='list_exact', score=0.5, score_kind='continuous', metrics={'f1': 0.5}),
              dict(answer_type='string_approximate', score=None, score_kind='binary', status='pending_judge', metrics={'llm_paraphrase': None})]
    code = 'print(4)\n'
    for index, grade in enumerate(grades):
        root = tmp_path / str(index) / 'single'
        root.mkdir(parents=True)
        records = {'report.json': dict(status='completed', runtime=1, usage={'total': usage}, cache={'groups': []},
                       budget={'limit_events': []}, infra_affected=False, communication={},
                       artifact_binding={'pipeline_code_sha256': hashlib.sha256(code.encode()).hexdigest()}),
                   'manifest.json': {'source_digest': 'fixture'}, 'submission.json': {'answer': 4, 'pipeline_code': code},
                   'native_response.json': {'code': code}, 'grade.json': grade}
        for name, data in records.items():
            (root / name).write_text(json.dumps(data))
        (root / 'trace.jsonl').touch()
    result = audit([tmp_path])['arms']['single']
    assert result['passed'] == result['binary_graded'] == 1
    assert result['continuous_graded'] == 2 and result['pending_judge'] == 1
    assert result['metric_groups']['numeric_approximate']['rae_score']['mean'] == 1
