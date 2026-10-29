import json
from types import SimpleNamespace

import pytest

from fakes import FakeRetriever
from benchmarks.browsecomp_plus.adapter import (CorpusTools, public_task, parse_plan,
    select_sample, valid_final, exact_grade)


def test_public_boundary_and_frozen_plan():
    request = public_task(dict(query='Find the person', answer='SECRET', gold_docs=['SECRET']))
    assert 'SECRET' not in request
    value = dict(members=[dict(role=role, assignment='Check a clue') for role in ('researcher', 'reviewer', 'leader')])
    plan = parse_plan(request, json.dumps(value))
    plan.validate_task(request)
    with pytest.raises(ValueError):
        plan.validate_task('different')
    value['members'][0]['role'] = 'invented'
    with pytest.raises(ValueError):
        parse_plan(request, json.dumps(value))


def test_sampling_ignores_answers_and_results():
    rows = [dict(query_id=str(i), query='Public clue. ' * 20, answer=str(i)) for i in range(12)]
    a = [r['query_id'] for r in select_sample(rows, {'1'})]
    for row in rows:
        row['answer'] = 'different'
    assert a == [r['query_id'] for r in select_sample(list(reversed(rows)), {'1'})]
    assert len(a) == 6 and '1' not in a


def test_real_tool_contract_and_exact_quote_windows():
    corpus = CorpusTools(FakeRetriever())
    tools = {t.name: t for t in corpus.tools()}
    call = lambda name, args: tools[name].run(args, SimpleNamespace(name='researcher'))
    hit = json.loads(call('search', dict(query='Alpha Prize', k=1)).text)['results'][0]
    docid = hit['docid']
    page = json.loads(call('open_document', dict(docid=docid, offset=4, limit=8)).text)
    assert page['text'] == hit['text'][4:12] and page['next_offset'] == 12
    matches = json.loads(call('find_in_document', dict(docid=docid, phrase='alpha')).text)
    assert matches['total_matches'] == 1
    assert hit['text'][matches['matches'][0]['match_offset']:].startswith('Alpha')
    assert call('search', dict(query='x', k=True)).meta['error']
    assert call('open_document', dict(docid=docid, offset=-1)).meta['error']
    assert call('search', dict(query='x', answer='forbidden')).meta['error']
    assert not corpus.errors


def test_final_shape_and_mismatch_is_not_automatically_wrong():
    assert valid_final(json.dumps(dict(answer='Maria Lopez', reasoning='Evidence', citations=[])))
    assert not valid_final(json.dumps(dict(answer='', reasoning='Evidence', citations=[])))
    assert exact_grade(' Maria LOPEZ ', 'Maria Lopez')['correct'] is True
    assert exact_grade('M. Lopez', 'Maria Lopez')['correct'] is None
    assert exact_grade('M. Lopez', 'Maria Lopez')['status'] == 'needs_review'
