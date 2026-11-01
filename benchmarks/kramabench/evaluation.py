"""Offline scalar numeric scoring, separated from model-visible task loading.

Ports the reviewed numeric branch of upstream Success at the pinned revision.
No upstream imports, eval(), judge calls, or execution of submitted code.
"""
import hashlib
import json
import math
from pathlib import Path
import subprocess

from harness.catalog import fingerprint
from .tasks import load_tasks, UPSTREAM_COMMIT


def numeric_success(predicted, target):
    if predicted is None:
        return 0
    def number(value):
        if isinstance(value, bool):
            raise ValueError("Boolean is not a scalar numeric answer")
        if isinstance(value, str):
            value = float(value.strip().removesuffix('%').strip())
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("Expected a finite scalar numeric answer")
        return value
    try:
        predicted, target = number(predicted), number(target)
    except (ValueError, TypeError):
        return 0
    if predicted == target:
        return 1
    if isinstance(predicted, int) and isinstance(target, int):
        return 0
    if target == 0:
        return int(abs(predicted) < 1e-6)
    difference = abs(predicted - target)
    return int(difference / abs(target) < 1e-6 or difference < 1e-6
               or difference < max(abs(predicted), abs(target)) * 1e-4)


def grade_numeric(upstream, task_id, submission_path):
    upstream = Path(upstream)
    tasks, provenance = load_tasks(upstream)
    task = next(t for t in tasks if t.id == task_id)
    rows = json.loads((upstream / 'workload' / (task.domain + '.json')).read_text())
    reference = next(row for row in rows if row['id'] == task_id)
    if reference['answer_type'] != 'numeric_exact':
        raise ValueError('Only offline numeric_exact scoring is implemented')
    metrics = upstream / 'benchmark/metrics.py'
    expected = subprocess.check_output(['git', '-C', str(upstream), 'show', UPSTREAM_COMMIT + ':benchmark/metrics.py'])
    if metrics.read_bytes() != expected:
        raise ValueError('Modified upstream metric source')
    submission_bytes = Path(submission_path).read_bytes()
    submission = json.loads(submission_bytes)
    predicted, target = submission['answer'], reference['answer']
    return {'task_id': task_id, 'metric': 'pinned_success_numeric_branch',
            'score': numeric_success(predicted, target), 'prediction': predicted, 'target': target,
            'strict_target_equality': predicted == target,
            'submission_sha256': fingerprint(submission),
            'submission_file_sha256': hashlib.sha256(submission_bytes).hexdigest(),
            'upstream_metrics_sha256': hashlib.sha256(expected).hexdigest(),
            'provenance': provenance, 'judge_calls': 0, 'pipeline_reexecuted': False,
            'scope': 'Final numeric answer only; not the upstream paid pipeline evaluator'}
