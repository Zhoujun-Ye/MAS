"""Offline E4 answer measurements; evidence/stance coding remains explicit, not guessed."""

import json
from pathlib import Path
import tempfile

from benchmarks.kramabench.evaluation import grade_answer
from common.io import read_json, write_json
from .e4_runtime import VARIANTS


def worker_evaluation(base,upstream,task):
    receipt=read_json(base/'worker-report.json',{})
    result=dict(status='report_unavailable',score=None,candidate_answer=None,
                verification='uncoded',stance='uncoded',coding_required=True,
                score_scope='Semantic correctness requires evidence-backed coding; strict candidate metrics are diagnostic only')
    if receipt.get('status')!='available':return result
    raw=receipt['text'].strip()
    # Accept a single fenced JSON object without repairing its contents.
    if raw.startswith('```') and raw.endswith('```'):
        lines=raw.splitlines();raw='\n'.join(lines[1:-1])
    try:
        packet=json.loads(raw)
        if not isinstance(packet,dict) or set(packet)!={'observations','checks','candidate_answer'}:
            raise ValueError('Unexpected report schema')
        if not isinstance(packet['observations'],str) or not isinstance(packet['checks'],list):
            raise ValueError('Unexpected report types')
        result.update(status='report_available',reported_checks=packet['checks'],candidate_answer=packet['candidate_answer'])
        if packet['candidate_answer'] is not None:
            with tempfile.TemporaryDirectory(prefix='mas-e4-candidate-') as temporary:
                path=Path(temporary)/'answer.json';write_json(path,dict(answer=packet['candidate_answer']))
                grade=grade_answer(upstream,task,path)
            if grade['status']=='pending_judge':raise ValueError('E4 has no paid judge authorization')
            result.update(strict_candidate_score=grade['score'],strict_candidate_grade=grade)
    except (ValueError,TypeError,KeyError):result['status']='report_format_deviation'
    return result


def summarize(plan,grades):
    if not plan.get('e4'):return None
    lookup={(g['seed'],g['task_id'],g['arm']):g for g in grades if g['arm'].startswith('e4_')}
    rows=[]
    for case in plan['e4']['manifest']['cases']:
        for seed in (0,1,2):
            for variant in VARIANTS:
                worker=lookup.get((seed,case['task_id'],'e4_worker_'+variant),{})
                lead=lookup.get((seed,case['task_id'],'e4_lead_'+variant),{})
                rows.append(dict(task_id=case['task_id'],seed=seed,variant=variant,
                    premise_strength=case['premise_strength'],premise_origin=case['premise_origin'],
                    worker=worker,lead=lead,
                    strict_candidate_correct_final_wrong=(worker.get('strict_candidate_score',worker.get('score'))==1 and lead.get('score')==0)
                        if worker.get('strict_candidate_score',worker.get('score')) is not None and lead.get('score') is not None else None,
                    correct_report_wrong_final=None,semantic_coding_required=True))
    return dict(cells=rows,scope='Targeted ten-task, immediate-first-report replay; separate from six-arm ITT.',
        coding='Evidence-backed verification and premise stance require trace coding; no lexical auto-labels or additional paid coders.',
        uptake='Correct-report/wrong-final is a diagnostic flag, not proof of uptake loss.')
