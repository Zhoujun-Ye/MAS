import hashlib
import json

import pytest

from harness.evidence_mas.decision import DecisionProtocol, extract_answers, host_check
from harness.evidence_mas.measurements import extract_measurements, measurement
from harness.evidence_mas.store import Store, StoreError
from harness.evidence_mas.hook import collect, response

TARGET = dict(quantity='body mass', statistic='population mean', population='adults',
              period='2020', unit='kg', dataset='input-v1')


def protocol(tmp_path):
    result = DecisionProtocol(Store(tmp_path / 'store', 'run'))
    result.initialize('Compute the population mean in kg for adults in 2020.')
    return result


def captured(p, data, call):
    return collect(p.store, dict(hook_event_name='PostToolUse', tool_name='Bash', tool_use_id=call,
                                tool_response={'stdout':json.dumps(data)},tool_input={'command':'python computation.py'}))


def select(p, value):
    view = p.view()
    for item in view['candidates']:
        p.read(candidate_id=item['id'])
    chosen = next(c for c in view['candidates'] if c['value']==value)
    return p.select(view['snapshot'],chosen['id'], {'task_quote':'population   mean\nin kg','criterion':'Task estimand'},
        {c['id']:'Different analysis option' for c in view['candidates'] if c['target_id']==chosen['target_id'] and c['id']!=chosen['id']})


def test_parameterized_results_group_by_estimand_not_analysis_option(tmp_path):
    p = protocol(tmp_path)
    for i, missing_policy in enumerate(('drop','zero')):
        values = [10, None, 20]
        data = [x for x in values if x is not None] if missing_policy=='drop' else [x or 0 for x in values]
        captured(p, measurement(sum(data)/len(data),TARGET,{'missing':missing_policy},answer_target=True),str(i))
    view = p.view()
    assert {c['value'] for c in view['candidates']} == {10,15}
    assert len({c['target_id'] for c in view['candidates']}) == 1 and view['conflict']
    select(p,15)
    assert p.check({'answer':15})['accepted']
    assert not p.check({'answer':10})['accepted']


@pytest.mark.parametrize('dimension', list(TARGET))
def test_different_target_dimensions_are_not_conflated(dimension):
    one = extract_measurements(measurement(10,TARGET,{}))[0]
    two = extract_measurements(measurement(20,dict(TARGET,**{dimension:'different'}),{}))[0]
    assert one['group'] != two['group']


def test_legacy_labels_are_only_possible_groups_and_never_gate(tmp_path):
    p = protocol(tmp_path)
    for call, value in [('a',10),('b',20)]:
        captured(p, {'mean':value},call)
    assert p.view()['intermediate'] == []
    view = p.view(detail=True)
    assert len(view['intermediate']) == 2
    assert {m['confidence'] for m in view['intermediate']} == {'possible'}
    assert not view['conflict'] and not view['candidates']
    assert p.check({'answer':20})['reason']=='no_comparable_conflict'
    assert extract_measurements('mean: 42 kg')[0]['value'] == 42
    assert extract_measurements('42\n2020\n') == []


def test_same_value_rerun_does_not_stale_choice(tmp_path):
    p = protocol(tmp_path)
    captured(p, {'answer':42}, 'a')
    captured(p, {'answer':43}, 'b')
    select(p,42)
    old = p.view()['snapshot']
    captured(p, {'answer':42}, 'rerun')
    assert old == p.view()['snapshot']
    assert p.check({'final_answer':'42'})['accepted']
    assert not p.check({'answer':'42'})['accepted']
    assert p.check({'final_answer':''})['reason']=='declared_incomplete'
    assert p.check({'answer':None})['reason']=='declared_incomplete'


def test_whole_json_literals_and_extra_metadata():
    assert extract_answers('  {\n "answer": 42,\n "unit": "kg"\n}') == [42]
    assert extract_answers("{'answer': 42, 'method': 'mean'}") == [42]
    assert extract_answers("__import__('os').system('false')") == []


def test_tables_preserve_column_and_row_context_without_claiming_equivalence():
    result = extract_measurements('method,mean,count\ndrop,15,2\nzero,10,3')
    assert len(result)==4 and all(r['confidence']=='possible' for r in result)
    means = [r for r in result if r['target']['column']=='mean']
    assert {r['value'] for r in means} == {10,15}
    assert means[0]['group'] != means[1]['group']
    assert extract_measurements('[1, 2, 3]') == []
    assert extract_measurements('drwx------ 3 1009 1010 4096 Nov 5 06:42 workspace') == []


def test_stopped_worker_unknown_call_is_not_permanently_pending(tmp_path):
    p = protocol(tmp_path)
    collect(p.store,dict(hook_event_name='SubagentStart',agent_id='w'))
    collect(p.store,dict(hook_event_name='PreToolUse',agent_id='w',tool_use_id='p',tool_name='Bash'))
    assert p.check({'answer':42})['reason']=='execution_pending'
    assert p.check({'answer':42},execution_finished=True)['reason']=='no_comparable_conflict'
    collect(p.store,dict(hook_event_name='SubagentStop',agent_id='w'))
    assert p.check({'answer':42})['reason']=='no_comparable_conflict'


@pytest.mark.parametrize('tool,args',[('Write',{'file_path':'submission.json'}),
    ('Edit',{'file_path':'/workspace/submission.json'}),('Bash',{'command':'python save.py > submission.json'})])
def test_worker_submission_guard_for_both_modes(tool,args):
    reply = response(dict(hook_event_name='PreToolUse',agent_id='w',tool_name=tool,tool_input=args),None)
    assert reply['hookSpecificOutput']['permissionDecision']=='deny'


def test_readonly_old_store_never_migrates_or_audits(tmp_path):
    p = protocol(tmp_path)
    captured(p,{'answer':42},'a')
    with p.store.connect() as db:
        db.execute('DROP INDEX observation_identity')
    before = {str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in p.store.root.rglob('*') if f.is_file()}
    ro = Store(p.store.root,'run',readonly=True)
    ro.call('obs.list',{})
    with pytest.raises(StoreError,match='Read-only'):
        ro.call('obs.capture',{'tool_name':'Bash','tool_input':{}},role='collector')
    assert before == {str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in p.store.root.rglob('*') if f.is_file()}


def test_corrupt_protocol_store_returns_rejection_not_a_grading_exception(tmp_path):
    root = tmp_path/'native-profile/evidence'
    root.mkdir(parents=True)
    (root/'store.sqlite').write_bytes(b'not sqlite')
    assert host_check(tmp_path,{'answer':42}) == {'accepted':False,'reason':'decision_state_invalid'}


def test_final_answers_compete_across_target_dimensions(tmp_path):
    p = protocol(tmp_path)
    captured(p, measurement(42, TARGET, {}, answer_target=True), 'a')
    assert p.check({'answer':42})['accepted']
    assert p.check({'answer':999})['reason'] == 'answer_mismatch'
    captured(p, measurement(45, dict(TARGET, population='children'), {}, answer_target=True), 'b')
    assert p.check({'answer':999})['reason'] == 'selection_missing'
    captured(p, {'answer':46}, 'c')
    assert len(p.view()['candidates']) == 3
    select(p, 42)
    assert p.check({'answer':42})['accepted']


@pytest.mark.parametrize('value', ['a title', ['one', 2]])
def test_non_numeric_measurement(value, tmp_path):
    p = protocol(tmp_path)
    captured(p, measurement(value, TARGET, {}, answer_target=True), 'a')
    assert p.check({'answer':value})['accepted']


def test_invalid_measurement_is_diagnostic_not_hint(tmp_path):
    p = protocol(tmp_path)
    captured(p, {'measurement':{'value':42,'target':{'quantity':'mean'}}}, 'a')
    view = p.view(detail=True)
    assert view['invalid_measurement_count'] == 1
    assert not view['intermediate'] and not view['candidates']


def test_successful_taskstop_retires_pending_worker(tmp_path):
    p = protocol(tmp_path)
    collect(p.store, dict(hook_event_name='SubagentStart', agent_id='w'))
    collect(p.store, dict(hook_event_name='PreToolUse', agent_id='w', tool_name='Bash', tool_use_id='b'))
    event = dict(tool_name='TaskStop', tool_input={'task_id':'w'}, tool_use_id='stop')
    collect(p.store, dict(event, hook_event_name='PreToolUse'))
    assert p.check({'answer':42})['reason'] == 'execution_pending'
    collect(p.store, dict(event, hook_event_name='PostToolUseFailure', error='failed'))
    assert p.check({'answer':42})['reason'] == 'execution_pending'
    collect(p.store, dict(event, tool_use_id='stop2', hook_event_name='PostToolUse', tool_response={'task_id':'w','task_type':'local_agent'}))
    assert p.check({'answer':42})['accepted']


def test_parse_cache_and_readonly_replay(tmp_path, monkeypatch):
    from harness.evidence_mas import decision
    p = protocol(tmp_path)
    captured(p, {'answer':42}, 'a')
    first = p.view()
    monkeypatch.setattr(decision, 'extract_measurements', lambda *a, **k: pytest.fail('cache missed'))
    assert p.view() == first
    ro = DecisionProtocol(Store(p.store.root, 'run', readonly=True))
    before = {str(f):f.read_bytes() for f in p.store.root.rglob('*') if f.is_file()}
    assert ro.view() == first
    assert before == {str(f):f.read_bytes() for f in p.store.root.rglob('*') if f.is_file()}


def test_prompt_only_has_identical_guidance_but_no_decision_tools(tmp_path):
    from harness.evidence_mas.cli import EvidenceMASCLI, workspace_guidance, worker_prompt
    assert workspace_guidance('full') == workspace_guidance('full-prompt-only')
    assert worker_prompt('full') == worker_prompt('full-prompt-only')
    args = EvidenceMASCLI().command('fixture', store_root=tmp_path, run_id='run',
        task_rules='limits', observer_target=tmp_path/'observer', mode='full-prompt-only')
    mcp = json.loads(args[args.index('--mcp-config')+1])['mcpServers']['evidence']['args']
    assert mcp[mcp.index('--protocol')+1] == 'observations-v1'
    assert mcp[mcp.index('--mode')+1] == 'observations'
    worker = json.loads(args[args.index('--agents')+1])['evidence-worker']
    assert not any('decision_' in t for t in worker['tools'])
    assert any('obs_read' in t for t in worker['tools'])


def test_new_target_interpretation_requires_renewed_review(tmp_path):
    p = protocol(tmp_path)
    captured(p, {'answer':42}, 'a')
    captured(p, {'answer':45}, 'b')
    select(p, 42)
    before = p.view()['snapshot']
    captured(p, measurement(42, TARGET, {}, answer_target=True), 'c')
    assert p.view()['snapshot'] != before
    assert p.check({'answer':42})['reason']=='selection_stale'
    select(p,42)
    assert p.check({'answer':42})['accepted']
    assert len(next(c for c in p.view()['candidates'] if c['value']==42)['interpretations']) == 2


def test_corrupt_cache_falls_back_and_readonly_miss_does_not_write(tmp_path):
    p = protocol(tmp_path)
    captured(p, {'answer':42}, 'a')
    ro = DecisionProtocol(Store(p.store.root, 'run', readonly=True))
    assert ro.check({'answer':42})['accepted']
    assert not (p.store.root/'parsed-output').exists()
    assert p.check({'answer':42})['accepted']
    cache = next((p.store.root/'parsed-output').glob('*.json'))
    cache.write_text('invalid')
    assert p.check({'answer':42})['accepted']
