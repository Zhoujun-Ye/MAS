"""Versioned host-only answer metrics with pinned references; no implicit judge."""
import ast
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import subprocess

from ._io import fingerprint
from .tasks import DOMAINS, load_tasks, UPSTREAM_COMMIT

METRICS = {
    'numeric_exact': ('success',), 'string_exact': ('success',),
    'numeric_approximate': ('mean_absolute_error', 'mean_squared_error', 'rae_score'),
    'list_exact': ('f1', 'precision', 'recall'),
    'list_approximate': ('f1_approximate',), 'string_approximate': ('llm_paraphrase',),
}
PRIMARY = {kind: names[-1] if kind == 'numeric_approximate' else names[0] for kind, names in METRICS.items()}
UPSTREAM_NUMERIC_POLICY = 'upstream_v2'
NUMERIC_POLICY = 'scale_aware_v3'
NUMERIC_POLICIES = (UPSTREAM_NUMERIC_POLICY, NUMERIC_POLICY)
NUMERIC_RELATIVE_TOLERANCE = 1e-4


def validate_numeric_policy(policy):
    if policy not in NUMERIC_POLICIES:
        raise ValueError('Unknown numeric policy: ' + str(policy))


def number(value, *, percent_fraction=False):
    if isinstance(value, bool):
        raise ValueError('Boolean is not a number')
    if isinstance(value, str):
        value = value.strip()
        percent = value.endswith('%')
        value = float(value.removesuffix('%').strip())
        if percent and percent_fraction:
            value /= 100
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('Expected a finite scalar number')
    return value


def numeric_success(predicted, target, *, numeric_policy=NUMERIC_POLICY):
    validate_numeric_policy(numeric_policy)
    try:
        predicted, target = number(predicted), number(target)
    except (ValueError, TypeError, OverflowError):
        return 0
    if predicted == target:
        return 1
    if isinstance(predicted, int) and isinstance(target, int):
        return 0
    if numeric_policy == NUMERIC_POLICY:
        # Unit-free comparison: a fixed absolute epsilon makes tiny references
        # accept zero, wrong signs and large relative errors.
        return int(target != 0 and abs(predicted-target) / abs(target) <= NUMERIC_RELATIVE_TOLERANCE)
    if target == 0:
        return int(abs(predicted) < 1e-6)
    difference = abs(predicted - target)
    return int(difference / abs(target) < 1e-6 or difference < 1e-6
               or difference < max(abs(predicted), abs(target)) * 1e-4)


def success(predicted, target, *, numeric_policy=NUMERIC_POLICY):
    try:
        number(predicted), number(target)
    except (ValueError, TypeError, OverflowError):
        return int(isinstance(predicted, str) and isinstance(target, str)
                   and predicted.strip().lower() == target.strip().lower())
    return numeric_success(predicted, target, numeric_policy=numeric_policy)


def as_list(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            try:
                value = ast.literal_eval(value)
            except (ValueError, SyntaxError):
                value = [part.strip() for part in value.split(',') if part.strip()]
    if not isinstance(value, (list, tuple)):
        raise ValueError('Expected a list answer')
    return list(value)


def list_metrics(predicted, target, *, approximate=False):
    target = as_list(target)
    try:
        predicted = as_list(predicted)
    except ValueError:
        return {'f1_approximate': 0.0} if approximate else dict(f1=0.0, precision=0.0, recall=0.0)
    matched, recall_count = set(), 0
    for t in target:
        for j, p in enumerate(predicted):
            if isinstance(t, str):
                equal = t.strip().lower() == str(p).strip().lower()
            else:
                try:
                    error = abs(number(p, percent_fraction=True)-number(t)) / max(abs(number(t)), 1e-12)
                    equal = error <= 0.01 if approximate else error < 1e-6
                except (ValueError, TypeError, OverflowError):
                    equal = False
            if equal:
                matched.add(j)
                recall_count += 1
                break
    recall = recall_count / len(target) if target else 1.0
    precision = len(matched) / len(predicted) if predicted else float(not target)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    if approximate:
        return dict(f1_approximate=f1)
    # Upstream precision/recall use unique type-sensitive matches, unlike F1.
    positives = set()
    for p in predicted:
        for t in target:
            if isinstance(p, str) and isinstance(t, str):
                if p.strip().lower() == t.strip().lower():
                    positives.add(p.strip().lower())
                    break
            elif not isinstance(p, (str, bool)) and not isinstance(t, (str, bool)):
                try:
                    if abs(number(p)-number(t)) / max(abs(number(t)), 1e-12) < 1e-6:
                        positives.add(p)
                        break
                except (ValueError, TypeError, OverflowError):
                    pass
    return dict(f1=f1, precision=len(positives)/len(predicted) if predicted else 0.0,
                recall=len(positives)/len(set(target)) if target else 0.0)


def score_answer(predicted, target, answer_type, *, paraphrase=None, numeric_policy=NUMERIC_POLICY):
    validate_numeric_policy(numeric_policy)
    if answer_type not in METRICS:
        raise ValueError('Unknown answer type: ' + str(answer_type))
    metrics = {name: None for name in METRICS[answer_type]}
    status, judge_calls = 'graded', 0
    if answer_type in {'numeric_exact', 'string_exact'}:
        metrics['success'] = success(predicted, target, numeric_policy=numeric_policy)
    elif answer_type == 'numeric_approximate':
        target = number(target, percent_fraction=True)
        try:
            predicted = number(predicted, percent_fraction=True)
            error = abs(predicted-target)
            squared = error*error
            metrics.update(mean_absolute_error=error if math.isfinite(error) else None,
                           mean_squared_error=squared if math.isfinite(squared) else None,
                           rae_score=1/(1+error/abs(target)) if target else None)
            if target == 0:
                status = 'undefined_relative_error'
            elif not math.isfinite(squared):
                status = 'numeric_overflow'
        except (ValueError, TypeError, OverflowError):
            status = 'invalid_prediction'
            metrics['rae_score'] = 0.0
    elif answer_type == 'string_approximate':
        if paraphrase is None:
            status = 'pending_judge'
        else:
            verdict = paraphrase(str(predicted), str(target))
            judge_calls = 1
            if type(verdict) is not bool:
                raise ValueError('Paraphrase judge must return an explicit boolean')
            metrics['llm_paraphrase'] = int(verdict)
    else:
        target = as_list(target)
        if answer_type == 'list_approximate' and any(isinstance(t, str) for t in target):
            raise ValueError('Approximate string-list judging requires an explicit evaluator')
        metrics = list_metrics(predicted, target, approximate=answer_type == 'list_approximate')
    primary = PRIMARY[answer_type]
    return dict(status=status, answer_type=answer_type, metrics=metrics, metric=primary,
                score=metrics[primary], score_kind='binary' if primary in {'success', 'llm_paraphrase'} else 'continuous',
                judge_calls=judge_calls)


def scoring_contract(upstream, *, numeric_policy=NUMERIC_POLICY):
    """Validate source AND metric mapping before any solver dispatch."""
    validate_numeric_policy(numeric_policy)
    root, hashes = Path(upstream), {}
    for relative in ('benchmark/metrics.py', 'benchmark/fixtures/answer_type_fixtures.json'):
        expected = subprocess.check_output(['git', '-C', str(root), 'show', UPSTREAM_COMMIT + ':' + relative])
        if (root / relative).read_bytes() != expected:
            raise ValueError('Modified upstream scoring source: ' + relative)
        hashes[relative] = hashlib.sha256(expected).hexdigest()
    mapping = {r['name']: tuple(r['metrics']) for r in json.loads((root / 'benchmark/fixtures/answer_type_fixtures.json').read_text())}
    if mapping != METRICS:
        raise ValueError('Unexpected upstream answer-type metric mapping')
    tasks, provenance = load_tasks(root)
    counts = Counter()
    for domain in DOMAINS:
        for row in json.loads((root / 'workload' / (domain + '.json')).read_text()):
            if row['answer_type'] not in METRICS:
                raise ValueError('Unsupported workload answer type')
            if row['answer_type'] == 'list_approximate' and any(isinstance(v, str) for v in as_list(row['answer'])):
                raise ValueError('Workload requires string-list semantic judging')
            counts[row['answer_type']] += 1
    contract = dict(version='pinned_answer_metrics_v2', source_sha256=hashes, answer_types=dict(counts),
                task_count=len(tasks), offline_tasks=len(tasks)-counts['string_approximate'],
                semantic_judge_tasks=counts['string_approximate'], provenance=provenance,
                policy='No implicit judge, unsafe eval, answer extraction, unit repair or pipeline execution')
    if numeric_policy == NUMERIC_POLICY:
        contract.update(version='scale_aware_answer_metrics_v3',
            local_evaluator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            numeric_success_policy=dict(name=NUMERIC_POLICY, relative_tolerance=NUMERIC_RELATIVE_TOLERANCE,
                absolute_tolerance=0, nonzero_reference_scale='abs(target)', zero_reference='exact zero only',
                integer_pairs='exact equality', boundary='inclusive'),
            compatibility='Pinned reference source; binary numeric comparison intentionally differs from upstream_v2. Other metrics unchanged.')
    return contract


def grade_answer(upstream, task_id, submission_path, *, paraphrase=None, numeric_policy=NUMERIC_POLICY):
    contract = scoring_contract(upstream, numeric_policy=numeric_policy)
    tasks, _ = load_tasks(upstream)
    task = next(t for t in tasks if t.id == task_id)
    rows = json.loads((Path(upstream) / 'workload' / (task.domain + '.json')).read_text())
    reference = next(row for row in rows if row['id'] == task_id)
    submission_bytes = Path(submission_path).read_bytes() if submission_path is not None else None
    submission = json.loads(submission_bytes) if submission_bytes is not None else {'answer': None}
    result = score_answer(submission['answer'], reference['answer'], reference['answer_type'],
                          paraphrase=paraphrase, numeric_policy=numeric_policy) if submission_bytes is not None else dict(
        status='invalid_submission', answer_type=reference['answer_type'], metrics={name: None if name in
        {'mean_absolute_error', 'mean_squared_error'} else 0.0 for name in METRICS[reference['answer_type']]},
        metric=PRIMARY[reference['answer_type']], score=0.0, score_kind='binary' if reference['answer_type'] in
        {'numeric_exact', 'string_exact', 'string_approximate'} else 'continuous', judge_calls=0)
    return dict(result, task_id=task_id, prediction=submission['answer'], target=reference['answer'],
                submission_sha256=fingerprint(submission) if submission_bytes is not None else None,
                submission_file_sha256=hashlib.sha256(submission_bytes).hexdigest() if submission_bytes is not None else None,
                scoring_contract=contract, pipeline_reexecuted=False,
                scope='Final answer metrics only; not upstream pipeline or subtask evaluation')
