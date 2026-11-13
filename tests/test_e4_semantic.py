"""Semantic overlays are evidence-bound, complete, offline, and non-destructive."""

from copy import deepcopy
from itertools import product
import json

import pytest

from common.io import fingerprint
from scripts.studies.causal_experiments import e4_semantic as semantic


def fixture():
    cells=[];annotations=[];rubric={}
    for task,seed,variant in product([f't{i}' for i in range(10)],range(3),semantic.VARIANTS):
        rubric[task]=dict(p=dict(text='A candidate source exists.',truth='false',origin='leader'))
        content='The supported answer is2; this is a narrative report, not a bare scalar.'
        report_packet=dict(candidate_answer=content,observations='observed',checks=[])
        raw=json.dumps(report_packet)
        source=dict(id='call',name='Bash',input=dict(command='inspect source'),completed=True,success=True,observation='observed')
        cell=dict(seed=seed,task_id=task,variant=variant,report_status='available',report_text=raw,
            report_sha256=fingerprint(raw),packet=report_packet,
            worker_tools=dict(call=source),lead_tools=dict(call=source),lead_pipeline='print(2)',
            lead_submission=dict(answer=2),worker_raw_grade=dict(score=0),lead_raw_grade=dict(score=1),
            reference=dict(answer=2,answer_type='numeric_exact'))
        quote=dict(kind='report',path=['candidate_answer'],quote=content)
        row=dict(seed=seed,task_id=task,variant=variant,report_sha256=cell['report_sha256'],
            answer=dict(status='answered',normalized=2,evidence=[quote],normalization_rule='explicit_answer_transcription'),
            premises=dict(p=dict(stance='challenge',checked=True,operationalized=False,
                evidence=[dict(kind='worker_tool',id='call',quote='inspect source')])),
            lead_normalized=2,uptake=dict(status='not_applicable',wrong_claim=None,claim_truth=None,evidence=[]))
        cells.append(cell);annotations.append(row)
    pack=dict(cells=cells,plan_sha256='plan',protected_sha256={})
    coding=dict(cells=annotations,rubric=rubric,pack_sha256=fingerprint(pack),plan_sha256='plan',coder='test analyst')
    return pack,coding


def rebind(pack,coding):
    coding['pack_sha256']=fingerprint(pack)


def test_ninety_prose_answers_are_rescored_without_changing_raw_scores():
    pack,coding=fixture();original=deepcopy(pack)
    result=semantic.analyze(pack,coding)
    assert pack==original and result['paid_calls']==0 and result['raw_scores_preserved']
    assert result['correct_answer_final_agreement']==dict(worker_correct=90,lead_correct=90,
        scope='Correct primary answer content, not every factual statement or reasoning step in a report')
    assert all(r['raw_candidate_score']==0 and r['semantic_grade']['score']==1 for r in result['cells'])


@pytest.mark.parametrize('change',['missing','duplicate','report_hash','pack_hash','plan_hash','absent_quote','missing_answer_quote','missing_operation_trace','uncompleted_check'])
def test_incomplete_or_unbound_coding_is_rejected(change):
    pack,coding=fixture();row=coding['cells'][0]
    if change=='missing':coding['cells'].pop()
    elif change=='duplicate':coding['cells'][-1]=deepcopy(row)
    elif change=='report_hash':row['report_sha256']='changed'
    elif change=='pack_hash':coding['pack_sha256']='changed'
    elif change=='plan_hash':coding['plan_sha256']='changed'
    elif change=='absent_quote':row['answer']['evidence'][0]['quote']='Gold-only information'
    elif change=='missing_answer_quote':row['answer']['evidence']=[]
    elif change=='missing_operation_trace':row['premises']['p'].update(operationalized=True,evidence=[])
    else:pack['cells'][0]['worker_tools']['call']['completed']=False;rebind(pack,coding)
    with pytest.raises(ValueError):semantic.analyze(pack,coding)


def test_unknown_answers_stay_unknown_with_full_assignment_bounds():
    pack,coding=fixture();row=coding['cells'][0]
    row['answer'].update(status='ambiguous',normalized=None)
    result=semantic.analyze(pack,coding);group=result['groups'][0]
    assert result['cells'][0]['semantic_grade'] is None
    assert group['assigned']==30 and group['scored']==29
    assert group['assigned_score_bounds']==[29/30,1]
    assert group['mean_among_answered']==1


def test_unavailable_report_cannot_be_semantically_filled():
    pack,coding=fixture();pack['cells'][0]['report_status']='unavailable';rebind(pack,coding)
    with pytest.raises(ValueError,match='Unavailable'):semantic.analyze(pack,coding)


@pytest.mark.parametrize('invalid',['arithmetic','operands','zero','boolean'])
def test_fraction_normalization_requires_cited_operands_and_exact_arithmetic(invalid):
    pack,coding=fixture();row=coding['cells'][0]
    row['answer']['normalization_rule']=dict(kind='explicit_fraction_percent',numerator=1,denominator=50)
    if invalid=='arithmetic':row['answer']['normalized']=3
    elif invalid=='zero':row['answer']['normalization_rule']['denominator']=0
    elif invalid=='boolean':row['answer']['normalization_rule']['numerator']=True
    with pytest.raises(ValueError):semantic.analyze(pack,coding)


def test_fraction_normalization_uses_report_counts_not_reference():
    pack,coding=fixture();row=coding['cells'][0];cell=pack['cells'][0]
    text='2 percent, calculated from1 of50 samples.'
    cell['packet']['candidate_answer']=text
    cell['report_text']=json.dumps(cell['packet'])
    cell['report_sha256']=fingerprint(cell['report_text']);row['report_sha256']=cell['report_sha256']
    row['answer']['evidence']=[dict(kind='report',path=['candidate_answer'],quote=text)]
    row['answer']['normalization_rule']=dict(kind='explicit_fraction_percent',numerator=1,denominator=50)
    rebind(pack,coding)
    assert semantic.analyze(pack,coding)['cells'][0]['semantic_grade']['score']==1


def test_lead_alias_is_a_secondary_view_not_an_original_grade_change():
    pack,coding=fixture();cell=pack['cells'][0];row=coding['cells'][0]
    cell['reference']=dict(answer='Delaware',answer_type='string_exact')
    cell['lead_submission']['answer']='DE';cell['lead_raw_grade']['score']=0
    row['lead_normalized']='Delaware';rebind(pack,coding)
    result=semantic.analyze(pack,coding)['cells'][0]
    assert result['lead_raw_score']==0 and result['lead_semantic_grade']['score']==1
    assert cell['lead_submission']['answer']=='DE'
    row['lead_normalized']='Not a standard alias'
    with pytest.raises(ValueError,match='Lead normalization'):semantic.analyze(pack,coding)


def test_wrong_report_adoption_needs_both_report_and_lead_evidence():
    pack,coding=fixture();row=coding['cells'][0]
    row['uptake'].update(status='adopted',wrong_claim='Source is present',claim_truth='incorrect',evidence=[])
    with pytest.raises(ValueError,match='both sides'):semantic.analyze(pack,coding)


def test_a_fake_decoded_packet_cannot_supply_a_gold_only_quote():
    pack,coding=fixture();pack['cells'][0]['packet']['candidate_answer']='Fabricated answer'
    coding['cells'][0]['answer']['evidence'][0]['quote']='Fabricated answer';rebind(pack,coding)
    with pytest.raises(ValueError,match='Decoded packet'):semantic.analyze(pack,coding)


def test_semantic_judge_tasks_are_rejected_even_without_worker_answer():
    pack,coding=fixture();pack['cells'][0]['reference']['answer_type']='string_approximate'
    coding['cells'][0]['answer'].update(status='abstained',normalized=None);rebind(pack,coding)
    with pytest.raises(ValueError,match='offline only'):semantic.analyze(pack,coding)


def test_a_challenged_sensitivity_check_is_not_counted_as_premise_adoption():
    pack,coding=fixture()
    coding['cells'][0]['premises']['p']['operationalized']=True
    with pytest.raises(ValueError,match='Testing a challenged hypothesis'):semantic.analyze(pack,coding)


def test_cli_refuses_to_write_inside_paid_evidence(tmp_path,monkeypatch):
    run=tmp_path/'paid';run.mkdir()
    monkeypatch.setattr(semantic,'collect',lambda *a:pytest.fail('Touched source before output isolation'))
    with pytest.raises(ValueError,match='outside paid evidence'):
        semantic.main(['--run',str(run),'--output',str(run/'overwrite.json')])
