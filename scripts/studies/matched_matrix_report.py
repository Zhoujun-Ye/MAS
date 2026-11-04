"""Export only scores and operational metadata, never questions or answers."""
import json
from collections import Counter
from pathlib import Path
import argparse


def read(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def lines(path):
    return [json.loads(s) for s in path.read_text().splitlines() if s.strip()] if path.exists() else []


def price(usage):
    if not usage:
        return None
    if 'prompt_tokens' in usage:
        if 'completion_tokens' not in usage:
            return None
        total = usage['prompt_tokens']
        hit = usage.get('prompt_cache_hit_tokens', 0)
        output = usage.get('completion_tokens', 0)
    else:
        if 'input_tokens' not in usage or 'output_tokens' not in usage:
            return None
        hit = usage.get('cache_read_input_tokens', 0)
        total = usage.get('input_tokens', 0) + hit + usage.get('cache_creation_input_tokens', 0)
        output = usage.get('output_tokens', 0)
    return ((total - hit) * .15 + hit * .003 + output * .6) / 1e6


def collect(root):
    summary = read(root / 'summary.json')
    if summary is None:
        raise ValueError('Batch has not finished')
    grade_by_id = {(r['benchmark'], r['task_id'], r['backend']): r for r in summary['grades']}
    result = []
    for item in summary['rows']:
        b, t, k = item['benchmark'], item['task_id'], item['backend']
        out = Path(item['run'])
        folder = out / t / k
        report = read(folder / 'report.json', {})
        grade = grade_by_id.get((b, t, k), {})
        target = root / 'grades' / b / t / k
        score, grade_status, judge_cost = None, grade.get('status'), None
        if b == 'kramabench':
            g = grade.get('grade') or {}
            score, grade_status = g.get('score'), g.get('status', grade_status)
            judge = read(target / 'result.json', {})
            judge_cost = price(judge.get('native_usage')) if judge else 0
        else:
            sql = lines(target / 's2sql-results.jsonl')
            judged = lines(target / 'judge-results.jsonl')
            if sql:
                score, grade_status, judge_cost = float(sql[0]['match']), 'sql_execution_match', 0
            elif judged:
                score, grade_status = judged[0].get('score'), judged[0].get('status')
                judge_cost = price((judged[0].get('raw_response') or {}).get('usage'))
            elif grade.get('judge_calls') == 0:
                judge_cost = 0
        accounting = report.get('accounting', {})
        audit = report.get('native_audit', report.get('single_agent_audit', report.get('subagents_audit', {})))
        if b == 'kramabench':
            native_summary = read(out / 'summary.json', {})
            native_rows = native_summary.get('rows', [])
            if native_rows:
                native_row = native_rows[0]
                accounting = native_row.get('accounting', accounting)
                audit = native_row.get('single_agent_audit', native_row.get('subagents_audit', audit))
        ledger = lines(folder / 'gateway-requests.jsonl')
        finished = [r for r in ledger if r.get('event') == 'finished']
        model = [r for r in finished if r.get('route') == '/anthropic/v1/messages']
        dispatched = [r for r in ledger if r.get('event') == 'dispatched' and r.get('route') == '/anthropic/v1/messages']
        web = [r for r in finished if r.get('route') in ('/v1/tools/search', '/v1/tools/fetch')]
        web_cost = sum(isinstance(r.get('http_status'), int) and 200 <= r['http_status'] < 300 for r in web) * .00075
        model_costs = [price(r.get('usage')) for r in model]
        model_cost = sum(model_costs) if model_costs and all(v is not None for v in model_costs) and len(model) == len(dispatched) else None
        plan = read(out / 'plan.json', {})
        prompt = (plan.get('prompts') or {}).get(t)
        if prompt is None and plan.get('backend_instructions'):
            prompt = dict(organization_characters=len(plan['backend_instructions'].get(k, '')))
        costs = [model_cost, web_cost, judge_cost]
        result.append(dict(benchmark=b, task_id=t, backend=k, status=item['status'], score=score,
            grade_status=grade_status, seconds=report.get('cli', {}).get('elapsed_seconds'),
            model_requests=len(dispatched), model_responses=len(model),
            request_efforts=dict(Counter(r.get('request_effort', 'unknown') for r in dispatched)),
            model_usd_offpeak=model_cost, web_usd_estimate=web_cost, judge_usd_offpeak=judge_cost,
            total_usd_offpeak=sum(costs) if all(v is not None for v in costs) else None,
            accounting=accounting.get('observed_totals'), by_role=accounting.get('by_role'),
            native_audit_passed=audit.get('passed'), subagent_starts=audit.get('subagent_starts'),
            subagent_stops=audit.get('subagent_stops'),
            reconciliation=report.get('integrity_audit', {}).get('gateway_reconciliation', {}).get('status'),
            prompt=prompt, evidence=str(folder)))
    return dict(run=root.name, authorization=summary['authorization'], account_delta=summary.get('account_delta'),
        groups=summarize(result), rows=result,
        limitations=['One attempt per task and condition; descriptive validation set, not a general superiority claim.',
            'Full-score counts include all selected tasks in denominator; unknown grades are reported separately.',
            'Costs are off-peak token-usage estimates plus successful-HTTP web estimates, not invoices.',
            'Usage from failed or unobserved requests is unknown; a run token does not authenticate process origin.',
            'Native lifecycle evidence does not establish substantive worker contribution.',
            'DataClaw scores use adapted per-part rubric; process metrics remain unavailable.'],
        price_source='https://api-docs.deepseek.com/quick_start/pricing/')


def summarize(result):
    groups = []
    for b in ('dataclawbench', 'hybriddeepresearch', 'kramabench', 'all'):
        for k in ('claude-code-single-agent', 'claude-code-subagents'):
            selected = [r for r in result if r['backend'] == k and (b == 'all' or r['benchmark'] == b)]
            known = [r['score'] for r in selected if r['score'] is not None]
            elapsed = [r['seconds'] for r in selected if r['seconds'] is not None]
            costs = [r['total_usd_offpeak'] for r in selected]
            groups.append(dict(benchmark=b, backend=k, attempts=len(selected), graded=len(known),
                full_score=sum(s == 1 for s in known),
                mean_score=sum(known)/len(selected) if b != 'all' and selected and len(known) == len(selected) else None,
                statuses=dict(Counter(r['status'] for r in selected)),
                mean_minutes=sum(elapsed)/len(elapsed)/60 if elapsed else None,
                time_coverage=len(elapsed), cost_coverage=sum(c is not None for c in costs),
                total_usd_offpeak=sum(costs) if all(c is not None for c in costs) else None,
                model_requests=sum(r['model_requests'] for r in selected),
                native_audit_passes=sum(r['native_audit_passed'] is True for r in selected)))
    return groups


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Report already exists')
    report = collect(args.run)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report['groups'], indent=2))
