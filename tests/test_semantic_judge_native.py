import json

import pytest

from benchmarks.kramabench import semantic_judge


def fake_grade(upstream, task_id, submission_path, *, paraphrase=None):
    base = dict(answer_type="string_approximate", status="pending_judge", score=None,
                prediction="candidate", target="reference", submission_file_sha256="frozen")
    if paraphrase is not None:
        base.update(status="scored", score=int(paraphrase("candidate", "reference")))
    return base


def test_semantic_judge_is_one_tool_free_request_and_no_retry(tmp_path, monkeypatch):
    monkeypatch.setattr(semantic_judge, "grade_answer", fake_grade)
    calls = []
    def call(body):
        calls.append(body)
        return dict(content=[dict(type="text", text='{"equivalent":true}')], usage=dict(input_tokens=12))
    options = dict(upstream=tmp_path, task_id="fixture", backend="deepagents",
                   submission_path=tmp_path / "submission.json", question="public", key="fixture-key",
                   output=tmp_path / "judge", call=call)
    result = semantic_judge.judge_once(**options)
    assert result["score"] == 1 and len(calls) == 1
    assert "tools" not in calls[0] and calls[0]["thinking"] == {"type": "disabled"}
    assert "fixture-key" not in (tmp_path / "judge/request.json").read_text()
    with pytest.raises(FileExistsError):
        semantic_judge.judge_once(**options)
    assert len(calls) == 1


def test_invalid_judge_verdict_is_ungraded_error_not_false(tmp_path, monkeypatch):
    monkeypatch.setattr(semantic_judge, "grade_answer", fake_grade)
    result = semantic_judge.judge_once(upstream=tmp_path, task_id="fixture", backend="claude-code",
        submission_path=tmp_path / "submission.json", question="public", key="fixture",
        output=tmp_path / "judge", call=lambda body: dict(content=[dict(type="text", text='{"equivalent":"true"}')]))
    assert result["status"] == "judge_error" and result["score"] is None
    assert result["attempted_calls"] == 1
