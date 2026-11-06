import json

import pytest

from harness.evidence_mas.decision import DecisionProtocol, PROTOCOL, extract_answers, host_check
from harness.evidence_mas.hook import collect, decision_guard
from harness.evidence_mas.mcp import Server
from harness.evidence_mas.store import Store, StoreError


@pytest.fixture
def protocol(tmp_path):
    store = Store(tmp_path / 'native-profile/evidence', 'benchmark-evidence')
    result = DecisionProtocol(store)
    result.initialize('Compute the population mean in kilograms, excluding missing observations.')
    return result


def capture(protocol, value, call='a', **kwargs):
    event = dict(hook_event_name='PostToolUse', tool_name='Bash', tool_use_id=call,
                 tool_input={'command':'python analysis.py'}, tool_response={'stdout':json.dumps({'answer':value})})
    event.update(kwargs)
    return collect(protocol.store, event)


def choose(protocol, value):
    view = protocol.view()
    candidate = next(c for c in view['candidates'] if c['value'] == value)
    return protocol.select(view['snapshot'], candidate['id'],
        {'task_quote':'population mean in kilograms', 'criterion':'Population, missingness and units match the task'},
        {c['id']:'Different aggregation or units' for c in view['candidates'] if c['id'] != candidate['id']})


def test_only_explicit_execution_answers_are_candidates(protocol):
    capture(protocol, 2)
    capture(protocol, 9, 'read', tool_name='Read')
    capture(protocol, 8, 'fail', hook_event_name='PostToolUseFailure')
    capture(protocol, 7, 'truncated', truncated=True)
    capture(protocol, 6, 'interrupt', tool_response={'stdout':'{"answer":6}', 'interrupted':True})
    assert [c['value'] for c in protocol.view()['candidates']] == [2]
    assert extract_answers('year 2025, answer is 4') == []
    assert extract_answers('{"answer":4,"unit":"kg"}') == [4]
    assert extract_answers({'stdout':'{"answer":4}', 'exit_code':1}) == []


def test_answer_matching_preserves_large_integer_precision():
    from harness.evidence_mas.decision import answer_key
    assert answer_key(10**35+1) != answer_key(10**35+2)
    assert answer_key(1) == answer_key(1.0)
    assert answer_key(0) == answer_key(-0.0)
    assert answer_key(True) != answer_key(1)


def test_selection_and_submission_consistency_and_staleness(protocol):
    capture(protocol, 2)
    capture(protocol, 3, 'b')
    assert protocol.check({'answer':2})['reason'] == 'selection_missing'
    choose(protocol, 2)
    assert protocol.check({'answer':2})['accepted']
    assert protocol.check({'answer':3})['reason'] == 'answer_mismatch'
    capture(protocol, 4, 'c')
    assert protocol.check({'answer':2})['reason'] == 'selection_stale'
    choose(protocol, 2)
    assert protocol.check({'answer':2})['accepted']


def test_no_automatic_correctness_or_majority_vote(protocol):
    capture(protocol, 2)
    capture(protocol, 3, 'b')
    capture(protocol, 3, 'c')
    view = protocol.view()
    assert len(view['candidates']) == 2
    assert all(set(c) == {'id','value','target_id','target','interpretations'} for c in view['candidates'])
    assert view == protocol.view()
    choose(protocol, 3)
    # A wrong semantic choice can still be consistent. The protocol must not claim otherwise.
    assert protocol.check({'answer':3})['semantic_validity'] == 'unverified'


def test_source_quotes_comparisons_and_role_enforced(protocol):
    capture(protocol, 2)
    capture(protocol, 3, 'b')
    view = protocol.view()
    candidate = view['candidates'][0]
    with pytest.raises(StoreError, match='alternative'):
        protocol.select(view['snapshot'], candidate['id'],
            {'task_quote':'population mean', 'criterion':'x'}, {})
    with pytest.raises(StoreError, match='verbatim'):
        protocol.select(view['snapshot'], candidate['id'],
            {'task_quote':'invented codebook', 'criterion':'x'}, {})
    with pytest.raises(StoreError, match='Only lead'):
        protocol.select(view['snapshot'], candidate['id'], {}, {}, role='worker')
    with pytest.raises(StoreError, match='frozen'):
        protocol.initialize('Replace task')


def test_four_tools_and_no_legacy_mutations(protocol):
    server = Server(protocol.store, 'lead', 'lead', protocol=PROTOCOL)
    server.initialized = True
    listing = server.handle(dict(jsonrpc='2.0', id=1, method='tools/list'))['result']['tools']
    assert len([t for t in listing if t['name'].startswith('decision_')]) == 4
    worker = Server(protocol.store, 'worker', 'worker', protocol=PROTOCOL)
    assert not worker.available('decision_select')
    assert not worker.available('decision_check')
    assert not server.available('ledger_propose')
    assert server.available('obs_read')


def test_hook_and_host_gate_cannot_be_bypassed_by_plain_file_write(protocol, tmp_path):
    capture(protocol, 2)
    capture(protocol, 3, 'alternative')
    event = dict(hook_event_name='PreToolUse', tool_name='Write',
                 tool_input={'file_path':'/workspace/submission.json', 'content':'{"answer":2}'})
    assert decision_guard(protocol.store, event)['hookSpecificOutput']['permissionDecision'] == 'deny'
    assert not host_check(tmp_path, {'answer':2})['accepted']
    choose(protocol, 2)
    assert decision_guard(protocol.store, event) is None
    assert host_check(tmp_path, {'answer':2})['accepted']
    assert not host_check(tmp_path, {'answer':3})['accepted']
    (protocol.store.root / 'degraded.jsonl').write_text('{}\n')
    assert not host_check(tmp_path, {'answer':2})['accepted']


def test_full_protocol_is_opt_in_and_baseline_unchanged():
    from scripts.common.evidence import configuration, lead_prompt
    from scripts.common.prompts.conditions import backend_instructions
    assert configuration('full')['protocol'] == PROTOCOL
    assert backend_instructions('claude-code-subagents') not in lead_prompt('full')
    assert 'decision_select' not in lead_prompt('observations')


def test_inflight_execution_blocks_commit(protocol):
    capture(protocol, 2)
    choose(protocol, 2)
    collect(protocol.store, dict(hook_event_name='SubagentStart', agent_id='worker'))
    collect(protocol.store, dict(hook_event_name='PreToolUse', tool_name='Bash', agent_id='worker',
        tool_use_id='pending', tool_input={'command':'compute'}))
    assert protocol.check({'answer':2})['reason'] == 'execution_pending'


def test_replay_is_read_only_and_gold_does_not_generate_candidates(tmp_path):
    from scripts.probes.replay_decisions import replay
    run = tmp_path / 'run'
    folder = run / 'task/backend'
    events = folder / 'native-profile/observer/events.jsonl'
    events.parent.mkdir(parents=True)
    events.write_text(json.dumps(dict(hook_event_name='PostToolUse', tool_name='Bash',
        tool_response={'stdout':'{"answer":1}'}))+'\n')
    (folder / 'workspace').mkdir()
    (folder / 'workspace/submission.json').write_text('{"answer":1}')
    (folder / 'report.json').write_text('{"grade":{"score":0,"target":2}}')
    summary = tmp_path / 'summary.json'
    summary.write_text(json.dumps({'rows':[dict(run=str(run),task_id='task',backend='backend',benchmark='kramabench')]}))
    before = {str(p):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    report = replay([summary])
    row = next(iter(report['aggregates'].values()))
    assert row['incorrect_gold_covered'] == 0 and row['covered_runs'] == 1
    assert row['incorrect_submitted_value_absent'] == 0
    assert before == {str(p):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
