import json
from types import SimpleNamespace

import pytest

from benchmarks.dataclawbench.evaluation import normalize_verdict, validate_verdict
from scripts.common.score import judge_rows


@pytest.mark.parametrize("flat", [False, True])
@pytest.mark.parametrize("answer,scores,total", [([1, 2], {"part_0": 1, "part_1": 0}, .5), ("gold", {"match": 1}, 1)])
def test_both_score_layouts_preserve_rubric(answer, scores, total, flat):
    verdict = dict(scores, total=total) if flat else dict(scores=scores, total=total)
    assert validate_verdict(answer, verdict) == total
    assert normalize_verdict(answer, verdict)["scores"] == scores


@pytest.mark.parametrize("verdict", [None, [], {"scores": []},
    {"part_0": 1, "total": 1}, {"part_0": 1, "part_1": 0, "extra": 1, "total": .5},
    {"scores": {"part_0": 1, "part_1": 0}, "part_0": 0, "total": .5},
    {"part_0": True, "part_1": 0, "total": .5}, {"part_0": 1, "part_1": 0, "total": 1},
    {"part_0": 1, "part_1": 0, "total": float("nan")},
    {"part_0": 1, "part_1": 0}, {"part_0": "1", "part_1": 0, "total": .5}])
def test_invalid_or_ambiguous_verdicts_still_fail(verdict):
    with pytest.raises(ValueError):
        validate_verdict([1, 2], verdict)


def test_live_reader_normalizes_once_and_retains_raw_response(tmp_path):
    raw = json.dumps(dict(part_0=1, part_1=0, total=.5, notes="fixture"))
    saved = dict(choices=[dict(message=dict(content=raw))])
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=raw))], model_dump=lambda: saved)
    requests = []
    def call(**kwargs):
        requests.append(kwargs)
        return response
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=call)))
    results = judge_rows([dict(task_id="fixture", task_prompt="question", response="candidate", answer=[1, 2])],
        benchmark="dataclawbench", upstream=tmp_path, model="fixture", output=tmp_path, client=client)
    assert len(requests) == 1
    assert results[0]["score"] == .5 and results[0]["status"] == "graded"
    assert results[0]["raw_response"] == saved
    assert results[0]["verdict"]["scores"] == {"part_0": 1, "part_1": 0}
