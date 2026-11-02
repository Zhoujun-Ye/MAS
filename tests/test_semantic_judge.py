"""One-call DeepSeek judging with scripted clients, no paid execution."""
import hashlib
import json
import threading

import pytest

from benchmarks.kramabench import semantic
from fakes import ScriptedClient
from harness.llm import ModelConfig, ProviderError


@pytest.mark.parametrize('response', ['{"equivalent": true}', '{"equivalent": false}', 'yes',
                                    '{"equivalent": "true"}', '{"equivalent": true, "extra": 1}'])
def test_judge_is_one_call_bound_to_submission_and_keeps_original_grade(tmp_path, monkeypatch, response):
    config = ModelConfig(model='deepseek-flash', retries=0)
    model_calls = []
    def factory(cfg):
        def policy(messages, tools, choice):
            model_calls.append(messages)
            assert not tools and len(messages) == 3
            assert 'PRIVATE_SOLVER_HISTORY' not in json.dumps(messages)
            return {'content': response}
        return ScriptedClient(policy)
    contract = {'fixture': True}
    monkeypatch.setattr(semantic, 'source_digest', lambda: 'source')
    monkeypatch.setattr(semantic, 'scoring_contract', lambda path: contract)
    (tmp_path / 'batch.json').write_text(json.dumps(dict(source_digest='source', scoring=contract, task_ids=['fixture'])))
    source = tmp_path / 'fixture/single'
    source.mkdir(parents=True)
    submission = b'{"answer": "candidate"}'
    (source / 'submission.json').write_bytes(submission)
    digest = hashlib.sha256(submission).hexdigest()
    original = dict(status='pending_judge', task_id='fixture', prediction='candidate', target='reference', submission_file_sha256=digest)
    (source / 'grade.json').write_text(json.dumps(original))
    before = (source / 'grade.json').read_bytes()
    def grade(root, task, submission_path, *, paraphrase):
        return dict(status='graded', score=int(paraphrase('candidate', 'reference')), submission_file_sha256=digest)
    monkeypatch.setattr(semantic, 'grade_answer', grade)
    result = semantic.adjudicate(tmp_path, tmp_path, config, {'models': {}}, threading.Event(), client_factory=factory)
    assert result['attempted_calls'] == len(model_calls) == 1
    assert (source / 'grade.json').read_bytes() == before
    valid = response in ('{"equivalent": true}', '{"equivalent": false}')
    overlay = tmp_path / 'semantic-grades/fixture/single/grade.json'
    assert overlay.exists() == valid
    assert result['results'][0]['trace_errors'] == []
    assert result['status'] == ('completed' if valid else 'finished_with_errors')
    if valid:
        assert json.loads(overlay.read_text())['score'] == int('true' in response)


def test_judge_contract_rejects_retries_and_scope_growth():
    with pytest.raises(ValueError):
        semantic.judge_contract(ModelConfig(model='deepseek-flash', retries=1))
    with pytest.raises(ValueError):
        semantic.judge_contract(ModelConfig(model='other'))
    with pytest.raises(ValueError):
        semantic.judge_contract(ModelConfig(model='deepseek-flash'), max_calls=31)


def test_judge_fatal_error_stops_further_calls_without_false_failure_score(tmp_path, monkeypatch):
    contract = {'fixture': True}
    monkeypatch.setattr(semantic, 'source_digest', lambda: 'source')
    monkeypatch.setattr(semantic, 'scoring_contract', lambda path: contract)
    (tmp_path / 'batch.json').write_text(json.dumps(dict(source_digest='source', scoring=contract, task_ids=['fixture'])))
    for arm in ('single', 'team_full'):
        directory = tmp_path / 'fixture' / arm
        directory.mkdir(parents=True)
        data = b'{"answer": "candidate"}'
        (directory / 'submission.json').write_bytes(data)
        (directory / 'grade.json').write_text(json.dumps(dict(status='pending_judge', task_id='fixture', prediction='candidate', target='reference', submission_file_sha256=hashlib.sha256(data).hexdigest())))
    calls = []
    def factory(cfg):
        def policy(*args):
            calls.append(True)
            raise ProviderError('http_402', 'fixture', 402)
        return ScriptedClient(policy)
    stop = threading.Event()
    result = semantic.adjudicate(tmp_path, tmp_path, ModelConfig(model='deepseek-flash'),
                                 {'models': {}}, stop, client_factory=factory, concurrency=1)
    assert stop.is_set() and len(calls) == result['attempted_calls'] == 1
    assert result['status'] == 'stopped_after_fatal' and result['not_started'] == 1
    assert not list((tmp_path / 'semantic-grades').glob('*/*/grade.json'))
