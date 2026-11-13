"""Evidence-bound, analyst-coded E4 analysis. No provider, judge or pipeline execution."""

import argparse
from collections import Counter
import hashlib
from itertools import product
import json
from pathlib import Path
import re
import statistics

from benchmarks.kramabench.evaluation import score_answer, scoring_contract
from analysis.stats import bootstrap_ci
from common.io import fingerprint, read_json, write_json
from .e4_runtime import VARIANTS
from .report import sign_flip


def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


def packet(text):
    raw=text.strip()
    if raw.startswith('```') and raw.endswith('```'):
        raw='\n'.join(raw.splitlines()[1:-1])
    try:
        data=json.loads(raw)
        return data if isinstance(data,dict) else None
    except ValueError:return None


def hooks(folder):
    path=folder/'native-profile/observer/events.jsonl'
    rows=[json.loads(x) for x in path.read_text().splitlines()]
    out={}
    for number,row in enumerate(rows,1):
        identity=row.get('tool_use_id')
        if not identity:continue
        event=row.get('hook_event_name')
        if event=='PreToolUse':
            out[identity]=dict(id=identity,line=number,name=row.get('tool_name'),input=row.get('tool_input'),
                agent_id=row.get('agent_id'),completed=False)
        elif event in {'PostToolUse','PostToolUseFailure'} and identity in out:
            out[identity].update(completed=True,success=event=='PostToolUse',
                observation=row.get('tool_response',row.get('error')),observation_line=number)
    return out


def collect(run):
    run=Path(run).resolve();plan=read_json(run/'plan.json');summary=read_json(run/'summary.json')
    if not summary.get('complete') or summary['plan_sha256']!=fingerprint(plan):
        raise ValueError('Require the complete, unchanged frozen E4 run')
    upstream=Path(plan['upstream']);contract=scoring_contract(upstream)
    references={}
    for path in (upstream/'workload').glob('*.json'):
        references.update({x['id']:dict(answer=x['answer'],answer_type=x['answer_type']) for x in read_json(path)})
    grades={(g['seed'],g['task_id'],g['arm']):g for g in summary['grades']}
    protected={}
    def protect(path):
        path=Path(path)
        if path.is_symlink() or not path.is_file():raise ValueError('Expected regular retained evidence')
        protected[str(path)]=sha(path)
    for name in ('plan.json','summary.json','execution.json','phases.sqlite'):
        if (run/name).exists():protect(run/name)
    for path in (upstream/'workload').glob('*.json'):protect(path)
    for name in ('benchmark/metrics.py','benchmark/fixtures/answer_type_fixtures.json'):protect(upstream/name)
    cells=[]
    for case,seed,variant in product(plan['e4']['manifest']['cases'],plan['seeds'],VARIANTS):
        task=case['task_id'];base=run/f'round-{seed}'/task
        wb=base/('e4_worker_'+variant);lb=base/('e4_lead_'+variant)
        wf=wb/task/'claude-code-single-agent';lf=lb/task/'claude-code-subagents'
        receipt=read_json(wb/'worker-report.json');lead=read_json(lb/'result.json')
        if lead['cli']['e4_replay']['binding']['report_sha256']!=fingerprint(receipt['text']):
            raise ValueError('Paired report binding mismatch')
        sub=read_json(lf/'submission.json');pipeline=lf/'workspace'/sub['pipeline_path']
        if not pipeline.resolve().is_relative_to((lf/'workspace').resolve()):raise ValueError('Unsafe retained pipeline path')
        saved=case['prefix'];transcript=lf/'native-profile/claude/projects/-workspace'/(saved['session_id']+'.jsonl')
        rows=[json.loads(x) for x in transcript.read_text().splitlines()]
        if rows[:len(saved['rows'])]!=saved['rows'] or rows[len(saved['rows'])]['message']['content'][0]['content']!=receipt['text']:
            raise ValueError('Retained native prefix/report changed')
        for folder in (wf,lf):
            for path in folder.rglob('*.jsonl'):
                if 'replay-workspace' not in path.parts:protect(path)
            for name in ('report.json','grade.json','submission.json','cli/stdout.log','cli/stderr.log','cli/prompt.txt'):
                path=folder/name
                if path.exists():protect(path)
        for path in (wb/'worker-report.json',wb/'result.json',lb/'result.json',pipeline,transcript):protect(path)
        if (wb/'worker-answer.json').exists():protect(wb/'worker-answer.json')
        cells.append(dict(seed=seed,task_id=task,variant=variant,question=case['question'],
            edits=case['edits'],premise_origin=case['premise_origin'],premise_strength=case['premise_strength'],
            report_status=receipt['status'],report_text=receipt.get('raw_result') or '',
            report_sha256=fingerprint(receipt.get('raw_result')),packet=packet(receipt.get('raw_result') or ''),
            worker_tools=hooks(wf),lead_tools=hooks(lf),lead_pipeline=pipeline.read_text(),
            lead_submission=sub,worker_raw_grade=grades[(seed,task,'e4_worker_'+variant)],
            lead_raw_grade=grades[(seed,task,'e4_lead_'+variant)],reference=references[task]))
    if len(cells)!=90:raise ValueError('Require all ninety assigned E4 cells')
    return dict(kind='e4-semantic-review-pack-v1',run=str(run),plan_sha256=fingerprint(plan),
        scoring_contract=contract,protected_sha256=protected,cells=cells,paid_calls=0)


def at_path(value,path):
    for key in path:value=value[key]
    return value


def evidence(cell,ref):
    kind=ref['kind']
    if kind=='report':value=at_path(cell['packet'],ref.get('path',[])) if ref.get('path') else cell['report_text']
    elif kind=='pipeline':value=cell['lead_pipeline']
    elif kind in {'worker_tool','lead_tool'}:
        tool=cell['worker_tools' if kind=='worker_tool' else 'lead_tools'][ref['id']]
        value=tool.get('observation') if ref.get('part')=='observation' else tool['input']
    else:raise ValueError('Unknown evidence kind')
    rendered=value if isinstance(value,str) else json.dumps(value,ensure_ascii=False)
    if not isinstance(ref.get('quote'),str) or not ref['quote'] or ref['quote'] not in rendered:
        raise ValueError('Coding quote is not present in its bound evidence')
    return ref


def validate(pack,coding):
    if coding.get('pack_sha256')!=fingerprint(pack) or coding.get('plan_sha256')!=pack['plan_sha256']:
        raise ValueError('Coding is not bound to this evidence pack')
    index={(x['seed'],x['task_id'],x['variant']):x for x in pack['cells']}
    rows=coding.get('cells',[]);keys=[(x['seed'],x['task_id'],x['variant']) for x in rows]
    if len(keys)!=90 or len(set(keys))!=90 or set(keys)!=set(index):
        raise ValueError('Exactly one coding for each of ninety assigned reports is required')
    rubric=coding['rubric']
    if set(rubric)!={c['task_id'] for c in pack['cells']}:raise ValueError('Incomplete premise rubric')
    for row in rows:
        cell=index[(row['seed'],row['task_id'],row['variant'])]
        if cell['packet']!=packet(cell['report_text']):raise ValueError('Decoded packet does not match the retained report text')
        if cell['report_status']=='available' and fingerprint(cell['report_text'])!=cell['report_sha256']:
            raise ValueError('Report text hash mismatch')
        if row.get('report_sha256')!=cell['report_sha256']:raise ValueError('Coding report hash mismatch')
        answer=row['answer'];status=answer['status']
        if status not in {'answered','partial','abstained','ambiguous','unavailable'}:raise ValueError('Invalid answer status')
        if status=='answered' and answer.get('normalized') is None:raise ValueError('Missing normalized answer')
        if status!='answered' and answer.get('normalized') is not None:raise ValueError('Do not resolve abstention using gold')
        if cell['report_status']=='unavailable' and status!='unavailable':raise ValueError('Unavailable report cannot be coded as answered')
        if status=='answered' and not answer.get('evidence'):raise ValueError('Answer normalization needs a quoted report')
        if any(ref['kind']!='report' for ref in answer.get('evidence',[])):raise ValueError('Answer must come from the report, not the gold or lead')
        if set(row['premises'])!=set(rubric[row['task_id']]):raise ValueError('Every target premise needs separate coding')
        refs=list(answer.get('evidence',[]))+list(row['uptake'].get('evidence',[]))
        rule=answer.get('normalization_rule')
        if isinstance(rule,dict):
            if rule.get('kind')!='explicit_fraction_percent' or any(type(rule.get(k)) is not int or rule[k]<=0 for k in ('numerator','denominator')):
                raise ValueError('Only an explicitly cited positive integer ratio can be arithmetically normalized')
            if abs(answer['normalized']-100*rule['numerator']/rule['denominator'])>1e-10:
                raise ValueError('Normalized ratio does not match the annotated operands')
            text='\n'.join(r['quote'] for r in answer['evidence']).replace(',','')
            if not all(re.search(r'(?<!\d)'+str(rule[k])+r'(?!\d)',text) for k in ('numerator','denominator')):
                raise ValueError('Ratio operands are not both present in the cited report')
        raw_lead=cell['lead_submission']['answer'];normalized_lead=row['lead_normalized']
        aliases={'DE':'Delaware','WV':'West Virginia','NJ':'New Jersey'}
        if normalized_lead!=raw_lead and (not isinstance(raw_lead,str) or aliases.get(raw_lead)!=normalized_lead):
            raise ValueError('Lead normalization must be identity or an explicit standard state abbreviation')
        for premise in row['premises'].values():
            if premise['stance'] not in {'conform','challenge','uncertain','not_addressed','unavailable'}:raise ValueError('Invalid premise stance')
            if type(premise['checked']) is not bool or type(premise['operationalized']) is not bool:raise ValueError('Invalid check/operation code')
            if premise['operationalized'] and not any(ref['kind']=='worker_tool' for ref in premise.get('evidence',[])):
                raise ValueError('Operationalization requires a worker tool citation')
            if premise['operationalized'] and premise['stance']!='conform':
                raise ValueError('Testing a challenged hypothesis is not retaining it as an answer-defining premise')
            if premise['checked'] and not any(ref['kind']=='worker_tool' and cell['worker_tools'][ref['id']].get('completed') for ref in premise.get('evidence',[])):
                raise ValueError('A performed check requires completed worker tool evidence')
            refs.extend(premise.get('evidence',[]))
        uptake=row['uptake']
        if uptake.get('claim_truth') not in {None,'incorrect','partial','ambiguous'}:raise ValueError('Invalid wrong-claim certainty')
        if uptake.get('claim_truth') and not uptake.get('wrong_claim'):raise ValueError('Wrong-claim classification needs the claim itself')
        if uptake['status'] not in {'adopted','corrected','not_used','unclear','not_applicable'}:raise ValueError('Invalid uptake code')
        if uptake['status']=='adopted' and (not uptake.get('wrong_claim') or not any(r['kind'] in {'pipeline','lead_tool'} for r in uptake.get('evidence',[]))
                or not any(r['kind'] in {'report','worker_tool'} for r in uptake.get('evidence',[]))):
            raise ValueError('Wrong-report uptake requires evidence on both sides')
        for ref in refs:evidence(cell,ref)
    return index


def analyze(pack,coding):
    index=validate(pack,coding);out=[]
    for row in coding['cells']:
        cell=index[(row['seed'],row['task_id'],row['variant'])]
        a=row['answer'];grade=None
        if cell['reference']['answer_type']=='string_approximate':raise ValueError('E4 semantic coding is offline only; semantic judge tasks are forbidden')
        if a['status']=='answered':
            ref=cell['reference'];grade=score_answer(a['normalized'],ref['answer'],ref['answer_type'])
            if grade.get('judge_calls') or grade['status']=='pending_judge':raise ValueError('Offline semantics must never invoke a judge')
        false=[name for name,r in coding['rubric'][row['task_id']].items() if r['truth']=='false' and r['origin']=='leader']
        operated=any(row['premises'][name]['operationalized'] for name in false)
        ref=cell['reference'];lead_grade=score_answer(row['lead_normalized'],ref['answer'],ref['answer_type'])
        out.append(dict(row,semantic_grade=grade,lead_semantic_grade=lead_grade,raw_candidate_score=cell['worker_raw_grade'].get('score'),
            lead_raw_score=cell['lead_raw_grade']['score'],lead_answer=cell['lead_submission']['answer'],
            leader_false_premise_task=bool(false),leader_false_premise_operationalized=operated,
            leader_false_premise_exposed=row['variant']!='task_only' and bool(false)))
    groups=[]
    for variant in VARIANTS:
        selected=[r for r in out if r['variant']==variant];scores=[r['semantic_grade']['score'] for r in selected if r['semantic_grade'] is not None]
        exposed=[r for r in selected if r['leader_false_premise_exposed']]
        wrong=[r for r in selected if r['uptake']['claim_truth']=='incorrect']
        groups.append(dict(variant=variant,assigned=len(selected),answer_statuses=dict(Counter(r['answer']['status'] for r in selected)),
            scored=len(scores),mean_among_answered=statistics.mean(scores) if scores else None,
            assigned_score_bounds=[sum(scores)/len(selected),(sum(scores)+len(selected)-len(scores))/len(selected)],
            false_premise_exposed=len(exposed),false_premise_operationalized=sum(r['leader_false_premise_operationalized'] for r in exposed),
            same_false_operation_without_brief=sum(r['leader_false_premise_operationalized'] for r in selected if r['leader_false_premise_task']) if variant=='task_only' else None,
            correct_answer_contents=sum(r['semantic_grade'] is not None and r['semantic_grade']['score']==1 for r in selected),
            wrong_report_present=len(wrong),wrong_report_adopted=sum(r['uptake']['status']=='adopted' for r in wrong),
            wrong_report_corrected=sum(r['uptake']['status']=='corrected' for r in wrong),
            qualified_report_misused=sum(r['uptake']['status']=='adopted' and r['uptake']['claim_truth']=='ambiguous' for r in selected),
            lead_raw_mean=statistics.mean(r['lead_raw_score'] for r in selected),
            lead_semantic_mean=statistics.mean(r['lead_semantic_grade']['score'] for r in selected)))
    tasks=[]
    for task in coding['rubric']:
        tasks.append(dict(task_id=task,rubric=coding['rubric'][task],variants={v:[r for r in out if r['task_id']==task and r['variant']==v] for v in VARIANTS}))
    correct=[r for r in out if r['semantic_grade'] is not None and r['semantic_grade']['score']==1]
    inherited=[r for r in out if r['leader_false_premise_exposed'] and r['leader_false_premise_operationalized']]
    premise_counts=[]
    for task in coding['rubric']:
        for pid,rubric in coding['rubric'][task].items():
            for variant in VARIANTS:
                chosen=[r['premises'][pid] for r in out if r['task_id']==task and r['variant']==variant]
                premise_counts.append(dict(task_id=task,premise_id=pid,variant=variant,**rubric,
                    stances=dict(Counter(p['stance'] for p in chosen)),checked=sum(p['checked'] for p in chosen),
                    operationalized=sum(p['operationalized'] for p in chosen)))
    contrasts=[]
    lookup={(r['task_id'],r['seed'],r['variant']):r for r in out}
    for field in ('lead_semantic_score','false_premise_operation'):
        ids=[t for t in coding['rubric'] if field=='lead_semantic_score' or any(
            r['truth']=='false' and r['origin']=='leader' for r in coding['rubric'][t].values())]
        value=lambda r:r['lead_semantic_grade']['score'] if field=='lead_semantic_score' else int(r['leader_false_premise_operationalized'])
        for treatment,control in (('open','verbatim'),('task_only','verbatim')):
            differences=[statistics.mean(value(lookup[(t,z,treatment)])-value(lookup[(t,z,control)]) for z in (0,1,2)) for t in ids]
            contrasts.append(dict(outcome=field,treatment=treatment,control=control,task_clusters=len(ids),
                mean_difference=statistics.mean(differences),ci95=bootstrap_ci(differences,samples=20000,seed=0),
                exact_task_sign_flip_p=sign_flip(differences),scope='Post-hoc descriptive task-cluster contrasts, not new confirmatory tests or provider-seeded pairs'))
    return dict(kind='e4-offline-semantic-analysis-v1',plan_sha256=pack['plan_sha256'],pack_sha256=fingerprint(pack),
        coding_sha256=fingerprint(coding),coder=coding['coder'],groups=groups,tasks=tasks,
        analyzer_sha256=sha(Path(__file__)),premise_counts=premise_counts,
        false_premise_propagation=dict(exposed_reports=sum(r['leader_false_premise_exposed'] for r in out),
            operationalized=len(inherited),lead_adopted=sum(r['uptake']['status']=='adopted' for r in inherited),
            lead_corrected=sum(r['uptake']['status']=='corrected' for r in inherited),
            scope='Only leader-origin false hypotheses; exclude task-origin typos, mixed source proposals and correct controls. Observed operations, not attributable causal failures.'),
        correct_answer_final_agreement=dict(worker_correct=len(correct),lead_correct=sum(r['lead_semantic_grade']['score']==1 for r in correct),
            scope='Correct primary answer content, not every factual statement or reasoning step in a report'),
        posthoc_contrasts=contrasts,
        cells=out,paid_calls=0,raw_scores_preserved=True,
        limitations=['Single unblinded Codex-assistant coding, not independent human or dual-rater adjudication.',
            'Normalization is evidence-backed transcription, never selecting an alternative using the reference.',
            'Unknown, ambiguous and absent answers remain unscored; available-answer means have different coverage. Bounds cover all assigned reports.',
            'False-premise operationalization is observed behavior, not a per-report counterfactual causal attribution.',
            'Matching wrong worker/lead methods is trace-consistent uptake, not necessarily unique worker mediation of a premise already in the lead prefix.',
            'Task-only removes the entire brief; one fixed historical prefix and only three repeats per task.'])


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--coding',type=Path);p.add_argument('--pack',type=Path)
    args=p.parse_args(argv);run=args.run.resolve();output=args.output.resolve()
    if output.exists() or output.is_relative_to(run):raise ValueError('Use a fresh derived output outside paid evidence')
    pack=read_json(args.pack) if args.pack else collect(run)
    if Path(pack['run']).resolve()!=run:raise ValueError('Pack belongs to a different run')
    if any(sha(Path(path))!=digest for path,digest in pack['protected_sha256'].items()):raise ValueError('Original paid evidence changed')
    result=analyze(pack,read_json(args.coding)) if args.coding else pack
    if any(sha(Path(path))!=digest for path,digest in pack['protected_sha256'].items()):raise ValueError('Original paid evidence changed during analysis')
    if args.coding:
        result['evidence_integrity']=dict(protected_files=len(pack['protected_sha256']),before_after_unchanged=True,
            manifest_sha256=fingerprint(pack['protected_sha256']))
    write_json(output,result)
    print(json.dumps(dict(output=str(output),cells=len(result['cells']),sha256=fingerprint(result),paid_calls=0)))
    return 0


if __name__=='__main__':raise SystemExit(main())
