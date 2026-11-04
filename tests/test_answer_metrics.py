"""Pinned answer-type coverage; no model, judge or submitted-code execution."""
import ast
import hashlib
import json
import logging
from pathlib import Path

import pytest

from benchmarks.kramabench.evaluation import (METRICS, grade_answer, list_metrics,
                                             score_answer, scoring_contract)


@pytest.mark.parametrize('prediction,target,expected', [
    (0.519, 0.519, 1.0), (110, 100, 1/1.1), ('50%', 0.5, 1.0),
    (0, -10, 0.5), ('invalid', 1, 0.0), (None, 1, 0.0),
])
def test_approximate_numbers_have_continuous_metrics(prediction, target, expected):
    result = score_answer(prediction, target, 'numeric_approximate')
    assert result['score'] == pytest.approx(expected)
    assert result['score_kind'] == 'continuous' and result['judge_calls'] == 0
    assert set(result['metrics']) == set(METRICS['numeric_approximate'])


def test_zero_relative_target_and_nonfinite_predictions_are_explicit():
    result = score_answer(0, 0, 'numeric_approximate')
    assert result['score'] is None and result['status'] == 'undefined_relative_error'
    assert result['metrics']['mean_absolute_error'] == 0
    for value in (True, float('nan'), float('inf'), {}, []):
        assert score_answer(value, 1, 'numeric_exact')['score'] == 0
        assert score_answer(value, 1, 'numeric_approximate')['status'] == 'invalid_prediction'
    overflow = score_answer(1e308, -1e308, 'numeric_approximate')
    assert overflow['status'] == 'numeric_overflow' and overflow['score'] == 0
    json.dumps(overflow, allow_nan=False)


def test_string_exact_and_percent_rules_match_metric_specific_contracts():
    assert score_answer(' Singapore ', 'singapore', 'string_exact')['score'] == 1
    assert score_answer('Sao Paulo', 'S\u00e3o Paulo', 'string_exact')['score'] == 0
    assert score_answer('50%', 50.0, 'numeric_exact')['score'] == 1
    assert score_answer(0.11, 10.87, 'numeric_exact')['score'] == 0
    assert score_answer({'answer': 10.87}, 10.87, 'numeric_exact')['score'] == 0


def test_lists_preserve_upstream_unordered_partial_matching_and_safe_literals(tmp_path):
    result = score_answer(['B', 'a'], ['A', 'b', 'c'], 'list_exact')
    assert result['metrics'] == pytest.approx(dict(f1=0.8, precision=1, recall=2/3))
    assert score_answer("('a', 'B')", ['A', 'b'], 'list_exact')['score'] == 1
    assert score_answer([1.009, -2.0], [1.0, -2.0], 'list_approximate')['score'] == 1
    assert score_answer([1.011, -2.0], [1.0, -2.0], 'list_approximate')['score'] == 0.5
    sentinel = tmp_path / 'must-not-exist'
    attack = "__import__('pathlib').Path(" + repr(str(sentinel)) + ").touch()"
    assert score_answer(attack, ['safe'], 'list_exact')['score'] == 0
    assert not sentinel.exists()


def test_semantic_judging_is_explicit_and_never_replaced_by_exact_matching():
    result = score_answer('same', 'same', 'string_approximate')
    assert result['status'] == 'pending_judge' and result['score'] is None and result['judge_calls'] == 0
    calls = []
    def judge(predicted, target):
        calls.append((predicted, target))
        return True
    result = score_answer('paraphrase', 'reference', 'string_approximate', paraphrase=judge)
    assert result['score'] == result['judge_calls'] == len(calls) == 1
    with pytest.raises(ValueError, match='boolean'):
        score_answer('a', 'b', 'string_approximate', paraphrase=lambda *args: 'yes')


def test_actual_pinned_workload_coverage_and_reference_self_scores(kramabench_upstream):
    root = kramabench_upstream
    contract = scoring_contract(root)
    assert contract['task_count'] == 104 and contract['offline_tasks'] == 94
    assert contract['semantic_judge_tasks'] == 10
    from benchmarks.kramabench.tasks import DOMAINS
    for domain in DOMAINS:
        for row in json.loads((root / 'workload' / (domain + '.json')).read_text()):
            result = score_answer(row['answer'], row['answer'], row['answer_type'])
            assert result['score'] == (None if row['answer_type'] == 'string_approximate' else 1), row['id']


def test_ports_agree_with_pinned_upstream_on_valid_metric_inputs(kramabench_upstream):
    root = kramabench_upstream
    scoring_contract(root)
    module = ast.parse((root / 'benchmark/metrics.py').read_text())
    # Extract only reviewed metric definitions; never import the paid interfaces.
    keep = {'str_to_float', 'try_convert_to_number', 'Success', 'MeanAbsoluteError',
            'MeanSquaredError', 'RAEScore', 'F1', 'Precision', 'Recall', 'F1Approximate'}
    definitions = [node for node in module.body if getattr(node, 'name', None) in keep]
    namespace = dict(Metric=object, List=list, json=json, logging=logging,
                     GPTInterface=lambda **kwargs: None)
    exec(compile(ast.Module(body=definitions, type_ignores=[]), '<pinned-metrics>', 'exec'), namespace)
    for predicted, target in [(4, 4), ('50%', 50.0), (' a ', 'A'), (100.005, 100.0),
                              (0, 4.638e-13), (5.107269247909184e-13, 4.638e-13), (1e-7, 0)]:
        assert score_answer(predicted, target, 'numeric_exact', numeric_policy='upstream_v2')['score'] == namespace['Success']()(predicted, target)[0]
    for predicted, target in [(0.519, 0.519), (110, 100), ('50%', 0.5), (-12, -10)]:
        result = score_answer(predicted, target, 'numeric_approximate')['metrics']
        for metric, cls in [('mean_absolute_error', 'MeanAbsoluteError'), ('mean_squared_error', 'MeanSquaredError'), ('rae_score', 'RAEScore')]:
            assert result[metric] == pytest.approx(namespace[cls]()(predicted, target)[0])
    for predicted, target in [(['B', 'a'], ['A', 'b', 'c']), ([1.0, 2.0], [2.0, 1.0]), (['1'], [1])]:
        result = list_metrics(predicted, target)
        for metric, cls in [('f1', 'F1'), ('precision', 'Precision'), ('recall', 'Recall')]:
            assert result[metric] == pytest.approx(namespace[cls]()(predicted, target)[0])
    assert score_answer([1.009], [1.0], 'list_approximate')['score'] == namespace['F1Approximate']()([1.009], [1.0])[0]


def test_grade_binds_exact_submission_and_rejects_scoring_source_mutation(tmp_path, monkeypatch):
    import benchmarks.kramabench.evaluation as evaluation
    from benchmarks.kramabench.tasks import Task, DOMAINS
    for domain in DOMAINS:
        path = tmp_path / 'workload' / (domain + '.json')
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps([dict(id=domain+'-fixture', answer=0.519, answer_type='numeric_approximate')]))
    fixture = json.dumps([dict(name=k, metrics=list(v)) for k, v in METRICS.items()]).encode()
    source = {"benchmark/metrics.py": b'# pinned fixture', 'benchmark/fixtures/answer_type_fixtures.json': fixture}
    for name, data in source.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    monkeypatch.setattr(evaluation.subprocess, 'check_output', lambda args: source[args[-1].split(':', 1)[1]])
    monkeypatch.setattr(evaluation, 'load_tasks', lambda root: ([Task(d+'-fixture', d, 'public') for d in DOMAINS], {}))
    submission = tmp_path / 'submission.json'
    submission.write_text('{"answer": 0.519}')
    result = grade_answer(tmp_path, 'wildfire-fixture', submission)
    assert result['score'] == 1 and result['metric'] == 'rae_score'
    assert result['submission_file_sha256'] == hashlib.sha256(submission.read_bytes()).hexdigest()
    missing = grade_answer(tmp_path, 'wildfire-fixture', None)
    assert missing['status'] == 'invalid_submission' and missing['score'] == 0
    assert missing['metrics']['mean_absolute_error'] is None
    (tmp_path / 'benchmark/metrics.py').write_text('modified')
    with pytest.raises(ValueError, match='Modified upstream'):
        scoring_contract(tmp_path)
