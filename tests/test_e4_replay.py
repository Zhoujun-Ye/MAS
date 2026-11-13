"""E4 prefix isolation, one-to-one pairing and explicit paid scope boundaries."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from common.io import fingerprint, read_json, write_json
from scripts.studies.causal_experiments import e4_runtime as runtime, e4_prepare, e4_trial, e4_report, run
from scripts.kramabench.cli_runtime import INSTRUCTIONS


def case():
    call=dict(type='tool_use',id='delegate',name='Agent',input=dict(prompt='The table has a states column.',subagent_type='Explore'))
    rows=[dict(type='user',uuid='first',parentUuid=None,sessionId='sid',message=dict(role='user',content=[dict(type='text',text='original task')])),
          dict(type='assistant',uuid='last',parentUuid='first',sessionId='sid',message=dict(role='assistant',content=[call]))]
    return dict(task_id='t',question='public question',premise_strength='asserted',premise_origin='leader',
        edits=[dict(before='has a states column',after='might have a states column: does it?')],
        prefix=dict(rows=rows,session_id='sid',call_id='delegate',brief=call['input']['prompt'],
                    agent_type='Explore',guidance={n:INSTRUCTIONS for n in ('AGENTS.md','CLAUDE.md')},
                    provenance=dict(prefix_sha256=fingerprint(rows))))


def test_edits_change_only_exact_spans_and_task_only_has_no_leader_premise():
    c=case()
    assert runtime.edited_brief(c,'verbatim')==c['prefix']['brief']
    assert runtime.edited_brief(c,'task_only')=='public question'
    assert runtime.edited_brief(c,'open')=='The table might have a states column: does it?.'
    c['edits'][0]['before']='absent'
    with pytest.raises(ValueError):runtime.edited_brief(c,'open')


def test_native_prefix_install_changes_only_the_paired_tool_result(tmp_path):
    c=case();saved=deepcopy(c)
    a=runtime.install_prefix(tmp_path/'a',c,'report A')
    b=runtime.install_prefix(tmp_path/'b',c,'report B')
    rows=lambda p:[json.loads(x) for x in Path(p).read_text().splitlines()]
    first,second=rows(a['path']),rows(b['path'])
    assert first[:-1]==second[:-1]==c['prefix']['rows']
    assert first[-1]['parentUuid']=='last'
    assert first[-1]['message']['content']==[dict(type='tool_result',tool_use_id='delegate',content='report A')]
    assert c==saved and a['prefix_sha256']==b['prefix_sha256']
    assert a['report_sha256']!=b['report_sha256']


def donor(tmp_path):
    c=case();folder=tmp_path/'donor'
    write_json(folder/'report.json',dict(cli=dict(native_result=dict(session_id='sid'))))
    path=folder/'native-profile/claude/projects/-workspace/sid.jsonl';path.parent.mkdir(parents=True)
    future=dict(type='assistant',uuid='future',message=dict(role='assistant',content=[dict(type='text',text='FUTURE GOLD ANSWER')]))
    path.write_text('\n'.join(json.dumps(r) for r in c['prefix']['rows']+[future]))
    events=folder/'native-profile/observer/events.jsonl';events.parent.mkdir()
    events.write_text(json.dumps(dict(hook_event_name='PreToolUse',tool_use_id='delegate',observer_received_at='2'))+'\n')
    (folder/'workspace').mkdir()
    for name in ('AGENTS.md','CLAUDE.md'):(folder/'workspace'/name).write_text(INSTRUCTIONS)
    (folder/'workspace/submission.json').write_text('FUTURE GOLD ANSWER')
    return folder


def test_prefix_extraction_never_copies_future_answers(tmp_path):
    p=runtime.prefix(donor(tmp_path))
    assert 'FUTURE GOLD ANSWER' not in json.dumps(p)
    assert p['rows'][-1]['uuid']=='last'
    assert set(p['guidance'])=={'AGENTS.md','CLAUDE.md'}


@pytest.mark.parametrize('failure',['mutation','guidance','parallel'])
def test_nonportable_prefixes_fail_closed(tmp_path,failure):
    folder=donor(tmp_path)
    if failure=='guidance':(folder/'workspace/CLAUDE.md').write_text('future answer')
    elif failure=='mutation':
        with (folder/'native-profile/observer/events.jsonl').open('a') as f:
            f.write(json.dumps(dict(hook_event_name='PostToolUse',tool_name='Bash',observer_received_at='1'))+'\n')
    else:
        path=folder/'native-profile/claude/projects/-workspace/sid.jsonl'
        rows=[json.loads(x) for x in path.read_text().splitlines()]
        rows[1]['message']['content'].append(dict(type='tool_use',name='Read',id='another',input={}))
        path.write_text('\n'.join(json.dumps(r) for r in rows))
    with pytest.raises(ValueError):runtime.prefix(folder)


def test_worker_scoring_does_not_call_null_candidate_wrong_or_infer_stance(tmp_path,monkeypatch):
    text=json.dumps(dict(observations='checked',checks=[dict(question='x',evidence='file',conclusion='yes')],candidate_answer=None))
    write_json(tmp_path/'worker-report.json',dict(status='available',text=text))
    monkeypatch.setattr(e4_report,'grade_answer',lambda *a:pytest.fail('Null candidate was graded'))
    result=e4_report.worker_evaluation(tmp_path,tmp_path,'t')
    assert result['score'] is None and result['stance']=='uncoded' and result['coding_required']


def test_worker_scoring_preserves_full_report_and_never_calls_judge(tmp_path,monkeypatch):
    receipt=dict(status='available',text=json.dumps(dict(observations='x',checks=[],candidate_answer=3)))
    write_json(tmp_path/'worker-report.json',receipt)
    monkeypatch.setattr(e4_report,'grade_answer',lambda *a:dict(status='graded',score=1))
    result=e4_report.worker_evaluation(tmp_path,tmp_path,'t')
    assert result['score'] is None and result['strict_candidate_score']==1
    assert read_json(tmp_path/'worker-report.json')==receipt
    assert not (tmp_path/'worker-answer.json').exists()


def test_narrative_candidate_zero_is_not_semantic_incorrectness(tmp_path,monkeypatch):
    text=json.dumps(dict(observations='checked',checks=[],candidate_answer='The answer is EACC, the Eastern Area.'))
    write_json(tmp_path/'worker-report.json',dict(status='available',text=text))
    monkeypatch.setattr(e4_report,'grade_answer',lambda *a:dict(status='graded',score=0))
    result=e4_report.worker_evaluation(tmp_path,tmp_path,'t')
    assert result['score'] is None and result['strict_candidate_score']==0
    assert result['coding_required'] and result['stance']=='uncoded'


def test_uncoded_historical_candidates_never_establish_semantic_uptake_loss():
    plan=dict(e4=dict(manifest=dict(cases=[dict(task_id='t',premise_strength='asserted',premise_origin='leader')])) )
    grades=[dict(seed=0,task_id='t',arm='e4_worker_verbatim',score=1),
            dict(seed=0,task_id='t',arm='e4_lead_verbatim',score=0)]
    cell=e4_report.summarize(plan,grades)['cells'][0]
    assert cell['strict_candidate_correct_final_wrong'] is True
    assert cell['correct_report_wrong_final'] is None and cell['semantic_coding_required']


def test_e4_unclaimed_trial_never_dispatches_or_reads_credentials(tmp_path,monkeypatch):
    write_json(tmp_path/'plan.json',dict(source_manifest={}))
    monkeypatch.setattr(e4_trial.shared,'source_manifest',lambda:{})
    monkeypatch.setattr(e4_trial.shared,'credential',lambda *a:pytest.fail('Unclaimed replay read credentials'))
    with pytest.raises(ValueError,match='one-shot'):
        e4_trial.main(['--plan',str(tmp_path/'plan.json'),'--credentials',str(tmp_path/'secret'),
            '--seed','0','--task','t','--arm','e4_worker_open','--execute'])


def test_scope_and_dependencies_are_exact():
    assert len(e4_prepare.CASES)==10 and len({c[0] for c in e4_prepare.CASES})==10
    assert run.session_counts({})==(630,540)
    assert run.session_counts(dict(e4={ 'worker_sessions':90 }))==(810,720)
    for variant in runtime.VARIANTS:
        assert run.dependent_arm('e4_worker_'+variant)=='e4_lead_'+variant
    assert run.dependent_arm('e4_lead_open') is None
