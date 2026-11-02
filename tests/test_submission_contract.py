import io
import json
import sys

import pytest
from jsonschema import Draft202012Validator

from benchmarks.kramabench.adapter import parse_submission
from benchmarks.kramabench.roles import ANSWER_SCHEMA
from harness.data_tools import INSPECT_SCRIPT


@pytest.mark.parametrize('answer,valid', [(68.5, True), ([1, 2], True), ('Yes', True),
    (None, True), ({'average_age_years': 68.5}, False), ([{'value': 1}], False)])
def test_answer_contract_rejects_wrappers_without_extracting_values(answer, valid):
    assert Draft202012Validator(ANSWER_SCHEMA).is_valid(answer) == valid
    text = json.dumps(dict(answer=answer, pipeline_code='print(1)', evidence='', unfinished=[]))
    if valid:
        assert parse_submission(text)['answer'] == answer
    else:
        with pytest.raises(ValueError, match='diagnostic object'):
            parse_submission(text)


@pytest.mark.parametrize('path,allowed', [('/', True), ('.', True), ('/etc', False), ('../', False)])
def test_listing_root_alias_does_not_grant_host_root(tmp_path, monkeypatch, path, allowed):
    (tmp_path / 'sample.csv').touch()
    monkeypatch.setattr(sys, 'stdin', io.StringIO(json.dumps(dict(root=str(tmp_path), path=path, operation='list'))))
    output = io.StringIO()
    monkeypatch.setattr(sys, 'stdout', output)
    if allowed:
        exec(compile(INSPECT_SCRIPT, 'inspection', 'exec'), {})
        assert json.loads(output.getvalue())['entries'][0]['path'] == 'sample.csv'
    else:
        with pytest.raises(ValueError, match='selected root'):
            exec(compile(INSPECT_SCRIPT, 'inspection', 'exec'), {})
