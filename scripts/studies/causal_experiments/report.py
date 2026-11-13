"""Read-only intention-to-treat means and task-cluster contrasts for the six arms."""

import argparse
from bisect import bisect_left,bisect_right
from itertools import product
import json
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from analysis.request_accounting import model_receipts
from analysis.stats import bootstrap_ci
from common.io import read_json, write_json
from scripts.studies.krama_repeats import finite_score
from scripts.studies.matched_matrix_report import price
from .runtime import ARMS

CONTRASTS=(('null_worker','native'),('native','single'),('recon_transplant','single'),
           ('self_brief','brief_prompt'),('brief_prompt','single'))


def sign_flip(values):
    """Meet-in-the-middle exact two-sided test; at most 2**15 half sums for 30 tasks."""
    values=[v for v in values if abs(v)>1e-12]
    target=abs(sum(values))
    if target<=1e-12:return 1.0
    middle=len(values)//2
    sums=lambda v:[sum(s*x for s,x in zip(signs,v)) for signs in product((-1,1),repeat=len(v))]
    first=sums(values[:middle]);second=sorted(sums(values[middle:]))
    extreme=sum(len(second)-bisect_left(second,target-a-1e-12)
                +bisect_right(second,-target-a+1e-12) for a in first)
    return min(1.0,extreme/(len(first)*len(second)))


def holm(pvalues):
    result=[None]*len(pvalues); previous=0
    ordered=sorted(((i,p) for i,p in enumerate(pvalues) if p is not None),key=lambda x:x[1])
    for rank,(index,p) in enumerate(ordered):
        previous=max(previous,min(1,(len(pvalues)-rank)*p));result[index]=previous
    return result


def summarize(plan,grades):
    cells={}
    for g in grades:
        key=(g['seed'],g['task_id'],g['arm'])
        if key in cells or g['arm'] not in ARMS or g['task_id'] not in plan['task_ids'] or g['seed'] not in (0,1,2):
            raise ValueError('Unexpected or duplicate causal study grade')
        cells[key]=g
    def view(ids):
        groups=[];contrasts=[]
        for arm in ARMS:
            values=[[cells.get((s,t,arm),{}).get('score') for t in ids] for s in (0,1,2)]
            means=[statistics.mean(v) if v and all(finite_score(x) for x in v) else None for v in values]
            groups.append(dict(arm=arm,tasks_per_round=len(ids),round_means=means,
                mean=statistics.mean(means) if all(v is not None for v in means) else None,
                sample_sd=statistics.stdev(means) if all(v is not None for v in means) else None))
        for treatment,control in CONTRASTS:
            differences=[]
            for t in ids:
                a=[cells.get((s,t,treatment),{}).get('score') for s in (0,1,2)]
                b=[cells.get((s,t,control),{}).get('score') for s in (0,1,2)]
                if not all(finite_score(x) for x in a+b):break
                differences.append(statistics.mean(x-y for x,y in zip(a,b)))
            complete=bool(ids) and len(differences)==len(ids)
            contrasts.append(dict(treatment=treatment,control=control,task_clusters=len(ids),
                mean_difference=statistics.mean(differences) if complete else None,
                descriptive_bootstrap_ci95=bootstrap_ci(differences,samples=20000,seed=0) if complete else [None,None],
                exact_task_sign_flip_p=sign_flip(differences) if complete else None,
                primary=(treatment,control)==CONTRASTS[0],
                inference='Preregistered primary alpha=.05; secondary p-values Holm-adjusted; no equivalence claim'))
        adjusted=holm([r['exact_task_sign_flip_p'] for r in contrasts[1:]])
        for row,p in zip(contrasts[1:],adjusted):row['holm_secondary_p']=p
        return dict(groups=groups,contrasts=contrasts)
    excluded=[t for t in plan['task_ids'] if any(
        (cells.get((s,t,a),{}).get('native_audit') or {}).get('passed') is not True
        or (cells.get((s,t,a),{}).get('manipulation_check') or {}).get('passed') is not True
        for s in (0,1,2) for a in ARMS)]
    return dict(raw_intention_to_treat=view(plan['task_ids']),
        paired_protocol_sensitivity=dict(excluded_tasks=excluded,**view([t for t in plan['task_ids'] if t not in excluded])),
        scope='All planned cells remain in raw means. Missing scores stay unknown; protocol filtering is secondary and shared across every arm/round.')


def report(root):
    plan=read_json(root/'plan.json');summary=read_json(root/'summary.json',{})
    result=summarize(plan,[g for g in summary.get('grades',[]) if g['arm'] in ARMS])
    accounting=[]
    availability=[];secondary=[]
    for row in summary.get('rows',[]):
        from .run import session_backend
        folder=Path(row['output'])/row['task_id']/session_backend(row['arm'])
        ledger=folder/'gateway-requests.jsonl'
        rows=[json.loads(line) for line in ledger.read_text().splitlines()] if ledger.exists() else []
        receipt=model_receipts(rows)
        costs=[price(r.get('usage')) for r in receipt['observed']]
        known=[v for v in costs if v is not None]
        accounting.append(dict(seed=row['seed'],task_id=row['task_id'],role=row['arm'],
            dispatched_requests=len(receipt['dispatched']),known_model_usd_offpeak_subtotal=sum(known) if known else None,
            unknown_model_cost_requests=max(len(receipt['dispatched']),len(receipt['terminal']))-len(known)))
        if row['arm']=='recon':
            donor=read_json(Path(row['output'])/'packet.json',{})
            availability.append(donor.get('status')=='available')
        elif row['arm'] in ARMS:
            events_path=folder/'native-profile/observer/events.jsonl'
            events=[json.loads(x) for x in events_path.read_text().splitlines()] if events_path.exists() else []
            lead=lambda r:not (r.get('agent_id') or '/subagents/' in str(r.get('transcript_path','')))
            started={r.get('agent_id') for r in events if r.get('hook_event_name')=='SubagentStart'}
            reports=[r.get('observer_received_at') for r in events if r.get('hook_event_name')=='SubagentStop'
                     and r.get('agent_id') in started and r.get('last_assistant_message')]
            writes=[r.get('observer_received_at') for r in events if lead(r) and r.get('hook_event_name')=='PostToolUse'
                    and r.get('tool_name')=='Write' and str((r.get('tool_input') or {}).get('file_path','')).endswith('/submission.json')]
            delay=None
            if reports and writes:
                from datetime import datetime
                delay=(datetime.fromisoformat(writes[0])-datetime.fromisoformat(reports[0])).total_seconds()
            submission=read_json(folder/'submission.json',{})
            provided=None if row['status'] in {'not_started','dispatch_unknown'} else submission.get('answer') is not None
            secondary.append(dict(seed=row['seed'],task_id=row['task_id'],arm=row['arm'],
                submission_file_present=(folder/'submission.json').is_file(),answer_provided=provided,
                delegation_calls=sum(lead(r) and r.get('hook_event_name')=='PreToolUse' and r.get('tool_name') in {'Agent','Task'} for r in events),
                report_to_observed_submission_write_seconds=delay,
                timing_scope='Hook emissions only; Bash-based writes or absent timestamps are unknown, and report emission is not verified incorporation'))
    from .e4_report import summarize as e4_summary
    return dict(result,e4=e4_summary(plan,summary.get('grades',[])),accounting=accounting,judge_calls=summary.get('judge_calls'),
        judge_cost_scope='Retained judge request/response receipts; model lower bounds above exclude judges',
        account_delta=summary.get('account_delta'),accounting_scope=summary.get('accounting_scope'),
        recon_availability=dict(available=sum(availability),assigned=plan['independent_recon_attempts'],observed=len(availability),
            rate=sum(availability)/plan['independent_recon_attempts'],observed_rate=sum(availability)/len(availability) if availability else None),secondary_outcomes=secondary,
        independent_recon_costs_included=True,complete=summary.get('complete',False),paid_calls=0)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args(argv)
    if args.output.exists() or args.output.resolve().is_relative_to(args.run.resolve()):
        raise ValueError('Use a fresh derived report outside immutable run evidence')
    result=report(args.run);write_json(args.output,result)
    print(json.dumps(result['raw_intention_to_treat'],indent=2));return 0


if __name__=='__main__':
    raise SystemExit(main())
