"""Read-only matched infra comparison; no solvers, judges or response payload export."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from analysis.timing import timing
from analysis.request_accounting import gateway_tokens
from analysis.native_evidence import tool_errors
from scripts.studies.matched_matrix_report import collect


def read(path):
    return json.loads(Path(path).read_text())


def complete_sum(values):
    return sum(values) if values and all(v is not None for v in values) else None


def change(before,after):
    if before is None or after is None:return dict(before=before,after=after,delta=None,percent=None)
    return dict(before=before,after=after,delta=after-before,
                percent=100*(after-before)/before if before else None)


def snapshot(row,pricing):
    folder=Path(row['evidence']);report=read(folder/'report.json')
    ledger=folder/'gateway-requests.jsonl'
    records=[json.loads(l) for l in ledger.read_text().splitlines()] if ledger.is_file() else []
    tokens=gateway_tokens(records)
    if not ledger.is_file():tokens.update(model_requests=None,model_completions=None)
    timing_ready=(ledger.is_file() and (folder/'native-profile/observer/events.jsonl').is_file()
                  and all(k in report for k in ('started_at','finished_at')))
    intervals=timing(folder,report)[0] if timing_ready else dict(available=False,reason='Missing timing evidence')
    errors=tool_errors(folder/'native-profile',row.get('runtime_backend',row['backend']),folder/'cli/stdout.log')
    errors.pop('native_state_write_commands',None)
    pdf_errors=set()
    for path in (folder/'native-profile').rglob('*.jsonl'):
        if 'observer' in path.parts:continue
        for line in path.read_text(errors='replace').splitlines():
            try:event=json.loads(line)
            except ValueError:continue
            content=(event.get('message') or {}).get('content')
            for block in content if isinstance(content,list) else []:
                if isinstance(block,dict) and block.get('type')=='tool_result' and block.get('is_error'):
                    if 'pdftoppm is not installed' in json.dumps(block.get('content')):
                        pdf_errors.add(block.get('tool_use_id'))
    rates=pricing['cny_per_million_offpeak'];cost=None
    if tokens['complete'] and row['web_usd_estimate'] is not None and row['judge_usd_offpeak']==0:
        cost=(tokens['uncached_input_tokens']*rates['cache_miss']+
              tokens['cache_hit_tokens']*rates['cache_hit']+tokens['output_tokens']*rates['output'])/1e6
        cost+=row['web_usd_estimate']/pricing['web_success_usd']*pricing['web_success_cny']
    return dict(seconds=row['seconds'],score=row['score'],status=row['status'],tokens=tokens,
        normalized_cny_offpeak=cost,normalized_usd_offpeak=row['total_usd_offpeak'],
        by_role=row['by_role'],native_audit_passed=row['native_audit_passed'],
        resources=row['resources'],timing=intervals,errors=errors,pdf_renderer_failures=len(pdf_errors),
        reconciliation=row['reconciliation'],native_retry_log_available=(folder/'cli/stdout.log').is_file())


def compare(before_root,after_root,pricing):
    before,after=collect(before_root),collect(after_root)
    manifests=[read(p/'task-manifest.json')['benchmarks'] for p in (before_root,after_root)]
    if manifests[0]!=manifests[1]:raise ValueError('Task IDs, hashes or order changed')
    settings=[dict(x['authorization']['protocol_settings']) for x in (before,after)]
    for s in settings:
        s.pop('cpu_per_attempt',None);s.pop('compute_threads',None)
    if settings[0]!=settings[1]:raise ValueError('Non-resource protocol settings changed')
    binaries=[x['authorization']['runtime_preflight']['binary_sha256'] for x in (before,after)]
    if binaries[0]!=binaries[1]:raise ValueError('Native CLI binary changed')
    keyed=[]
    for report in (before,after):
        rows={(r['benchmark'],r['task_id'],r['backend']):r for r in report['rows']}
        if len(rows)!=len(report['rows']):raise ValueError('Duplicate task/condition rows')
        keyed.append(rows)
    if not keyed[0] or set(keyed[0])!=set(keyed[1]):raise ValueError('Matched scope differs')
    pairs=[]
    for key,old in keyed[0].items():
        new=keyed[1][key]
        if old['prompt']!=new['prompt']:raise ValueError('Solver prompt changed')
        pairs.append(dict(benchmark=key[0],task_id=key[1],backend=key[2],
            before=snapshot(old,pricing),after=snapshot(new,pricing)))
    groups=[]
    for backend in dict.fromkeys(p['backend'] for p in pairs):
        selected=[p for p in pairs if p['backend']==backend];values={}
        for phase in ('before','after'):
            rows=[p[phase] for p in selected];tokens={k:complete_sum([r['tokens'][k] for r in rows])
                for k in ('input_tokens','cache_hit_tokens','uncached_input_tokens','output_tokens')}
            seconds=complete_sum([r['seconds'] for r in rows])
            values[phase]=dict(tokens,mean_seconds=seconds/len(rows) if seconds is not None else None,
                normalized_cny_offpeak=complete_sum([r['normalized_cny_offpeak'] for r in rows]),
                normalized_usd_offpeak=complete_sum([r['normalized_usd_offpeak'] for r in rows]),
                model_requests=complete_sum([r['tokens']['model_requests'] for r in rows]),
                cache_hit_rate=tokens['cache_hit_tokens']/tokens['input_tokens'] if tokens['input_tokens'] else None,
                full_scores=sum(r['score']==1 for r in rows),known_scores=sum(r['score'] is not None for r in rows),
                statuses=dict(Counter(r['status'] for r in rows)),
                native_audit_passes=sum(r['native_audit_passed'] is True for r in rows),
                pdf_renderer_failures=sum(r['pdf_renderer_failures'] for r in rows),
                reported_tool_errors=sum(r['errors']['reported_tool_errors'] for r in rows))
        groups.append(dict(backend=backend,attempts_per_phase=len(selected),**values,
            changes={k:change(values['before'][k],values['after'][k]) for k in
                     ('mean_seconds','uncached_input_tokens','output_tokens','normalized_cny_offpeak','model_requests')}))
    return dict(before=before_root.name,after=after_root.name,groups=groups,pairs=pairs,pricing=pricing,
        shared_account_delta=dict(before=before['account_delta'],after=after['account_delta']),paid_calls=0,
        limitations=['One stochastic observation per task/condition; bundled changes do not identify CPU causality.',
            'Later cache warmth, provider load, live search results and order may affect both runs.',
            'Gateway usage totals require complete request reconciliation; native role usage is observational.',
            'Common off-peak prices normalize cost; shared-account deltas and estimates are not invoices.',
            'Correctness, native policy compliance and resource/proxy health are separate measurements.'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before',required=True,type=Path)
    parser.add_argument('--after',required=True,type=Path)
    parser.add_argument('--pricing',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    report=compare(args.before,args.after,read(args.pricing))
    inputs={args.pricing,Path(__file__)}
    for root in (args.before,args.after):
        inputs.update((root/'summary.json',root/'task-manifest.json'))
    for pair in report['pairs']:
        for phase,root in (('before',args.before),('after',args.after)):
            summary=read(root/'summary.json')
            item=next(r for r in summary['rows'] if
                (r['benchmark'],r['task_id'],r['backend'])==(pair['benchmark'],pair['task_id'],pair['backend']))
            folder=Path(item['run'])/pair['task_id']/pair['backend']
            inputs.update((folder/'report.json',folder/'gateway-requests.jsonl',folder/'cli/stdout.log'))
            inputs.update((folder/'native-profile').rglob('*.jsonl'))
    report['provenance']={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(inputs) if p.is_file()}
    with args.output.open('x') as stream:json.dump(report,stream,indent=2)
    print(json.dumps(dict(groups=report['groups'],shared_account_delta=report['shared_account_delta'])))


if __name__=='__main__':main()
