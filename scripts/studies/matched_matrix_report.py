"""Export only scores and operational metadata, never questions or answers."""
import json
import csv
from collections import Counter
from decimal import Decimal
from pathlib import Path
import argparse
import copy
import math
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from benchmarks._external import jsonl
from common.io import read_json as read
from analysis.request_accounting import model_receipts, gateway_tokens
from scripts.common.prompts.conditions import runtime_backend
from harness.runtime_support.admission import infrastructure_health
from analysis.native_evidence import single_agent_violated

SINGLE_VIOLATION = 'single_agent_condition_violated'
COMPLIANCE_POLICY = ('Confirmed Single violations receive zero compliant score with the selected-task '
                     'denominator unchanged; raw answer scores and incurred costs are retained. '
                     'Missing lifecycle evidence alone is not a confirmed violation.')


def confirmed_single_violation(backend, records, *, audit=None, accounting=None):
    return backend == 'claude-code-single-agent' and (
        any(r.get('status') == SINGLE_VIOLATION or r.get('condition_status') == SINGLE_VIOLATION
            or single_agent_violated(r.get('single_agent_audit') or r.get('native_audit') or {},
                                     r.get('accounting')) for r in records)
        or single_agent_violated(audit or {}, accounting))


def normalize_compliance(report):
    """Correct derived exports without changing raw evidence or answer grades."""
    result = copy.deepcopy(report)
    for row in result['rows']:
        if confirmed_single_violation(row.get('runtime_backend', row['backend']), [row],
                audit=row, accounting=dict(by_role=row.get('by_role') or {})):
            row.update(condition_status=SINGLE_VIOLATION, compliant_score=0, protocol_accepted=False)
    result['groups'] = summarize(result['rows'])
    result['compliance_policy'] = COMPLIANCE_POLICY
    return result


def lines(path):
    return jsonl(path) if path.exists() else []


def price(usage):
    if not isinstance(usage, dict) or not usage:
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
        parts = [usage['input_tokens'], hit, usage.get('cache_creation_input_tokens', 0)]
        if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in parts):
            return None
        total = sum(parts)
        output = usage.get('output_tokens', 0)
    if (any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in (total, hit, output))
            or hit > total):
        return None
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
        actual_backend=item.get('runtime_backend',runtime_backend(k) if k == 'native' else k)
        folder = out / t / actual_backend
        report = read(folder / 'report.json', {})
        grade = grade_by_id.get((b, t, k), {})
        target = root/'grades'/k/b/t/actual_backend if item.get('evidence_mode') else root/'grades'/b/t/k
        if grade.get('grading_artifact'):
            target=Path(grade['grading_artifact'])
        score, grade_status, judge_cost = None, grade.get('status'), None
        if b == 'kramabench':
            g = grade.get('grade') or {}
            score, grade_status = g.get('score'), g.get('status', grade_status)
            judge = read(target / 'result.json', {})
            judge_cost = price(judge.get('native_usage')) if judge else 0
            if grade.get('reused_without_dispatch'):
                judge_cost=0  # Incremental batch expense; the original receipt retains incurred cost.
        else:
            sql = lines(target / 's2sql-results.jsonl')
            judged = lines(target / 'judge-results.jsonl')
            if sql:
                score, grade_status, judge_cost = float(sql[0]['match']), 'sql_execution_match', 0
            elif judged:
                score, grade_status = judged[0].get('score'), judged[0].get('status')
                judge_cost = (0 if judged[0].get('attempted_calls')==0 else
                              price((judged[0].get('raw_response') or {}).get('usage')))
            elif grade.get('judge_calls') == 0:
                judge_cost = 0
        accounting = report.get('accounting', {})
        native_row = report
        audit = report.get('native_audit', report.get('single_agent_audit', report.get('subagents_audit', {})))
        if b == 'kramabench':
            native_summary = read(out / 'summary.json', {})
            native_rows = native_summary.get('rows', [])
            if native_rows:
                native_row = native_rows[0]
                accounting = native_row.get('accounting', accounting)
                audit = native_row.get('single_agent_audit', native_row.get('subagents_audit', audit))
        ledger = lines(folder / 'gateway-requests.jsonl')
        receipts = model_receipts(ledger)
        model, dispatched = receipts['terminal'], receipts['dispatched']
        web = [r for r in ledger if r.get('event') in {'finished','shutdown'}
               and r.get('route') in ('/v1/tools/search', '/v1/tools/fetch') and r.get('upstream_attempted') is True]
        # Old receipts lack nonempty-result/billability evidence. Keep their
        # successful-HTTP estimate explicitly separate from the new metadata.
        web_estimates=[r.get('estimated_cost_usd') for r in web]
        legacy_web=any('estimated_cost_usd' not in r for r in web)
        web_cost=(sum(web_estimates) if all(v is not None for v in web_estimates) else None)
        if legacy_web:
            web_cost=sum(isinstance(r.get('http_status'),int) and 200<=r['http_status']<300 for r in web)*.00075
        web_sent=[r for r in ledger if r.get('event')=='dispatched'
                  and r.get('route') in ('/v1/tools/search','/v1/tools/fetch')]
        if web_sent and ({r.get('request_id') for r in web_sent}!={r.get('request_id') for r in web}
                         or len(web_sent)!=len(web)):
            web_cost=None
        model_costs = [price(r.get('usage')) for r in receipts['observed']]
        model_cost = sum(model_costs) if receipts['complete'] and all(v is not None for v in model_costs) else None
        known_costs = [v for v in model_costs if v is not None]
        plan = read(out / 'plan.json', {})
        prompt = (plan.get('prompts') or {}).get(t)
        if prompt is None and plan.get('backend_instructions'):
            prompt = dict(organization_characters=len(plan['backend_instructions'].get(actual_backend, '')))
        costs = [model_cost, web_cost, judge_cost]
        result.append(dict(benchmark=b, task_id=t, backend=k, runtime_backend=actual_backend, status=item['status'], score=score,
            **infrastructure_health(folder / 'gateway-requests.jsonl'),
            native_surface=report.get('native_surface'),
            resources=report.get('resources'),
            grade_status=grade_status, seconds=report.get('cli', {}).get('elapsed_seconds'),
            model_requests=len(dispatched), model_responses=sum(r.get('event') == 'finished' for r in model),
            model_tokens=gateway_tokens(ledger), model_request_outcomes=receipts['outcomes'],
            requests_with_known_cost=len(known_costs),
            requests_with_unknown_cost=max(len(dispatched),len(model))-len(known_costs) if dispatched or model else None,
            known_model_usd_offpeak_subtotal=sum(known_costs) if known_costs else None,
            cli_timing=report.get('cli', {}).get('timing'), container_cleanup=report.get('cleanup'),
            request_efforts=dict(Counter(r.get('request_effort') or
                ('not_applicable' if r.get('request_parameters', {}).get('thinking') == 'disabled' else 'unknown')
                for r in dispatched)),
            model_usd_offpeak=model_cost, web_usd_estimate=web_cost, judge_usd_offpeak=judge_cost,
            web_cost_basis='legacy successful-HTTP estimate; billability unverified' if legacy_web else 'host per-request billability receipts; not an invoice',
            total_usd_offpeak=sum(costs) if all(v is not None for v in costs) else None,
            accounting=accounting.get('observed_totals'), by_role=accounting.get('by_role'),
            native_audit_passed=audit.get('passed'), subagent_starts=audit.get('subagent_starts'),
            subagent_stops=audit.get('subagent_stops'),
            reconciliation=report.get('integrity_audit', {}).get('gateway_reconciliation', {}).get('status'),
            prompt=prompt, evidence=str(folder)))
        if item.get('evidence_mode'):
            result[-1].update(evidence_mode=item['evidence_mode'],evidence_workspace=report.get('evidence_workspace'))
        gate = report.get('decision_gate')
        result[-1].update(raw_score=score, compliant_score=0 if gate and not gate['accepted'] else score,
                          protocol_accepted=gate.get('accepted') if gate else None)
        if confirmed_single_violation(actual_backend, [item, report, native_row, grade],
                audit=audit, accounting=accounting):
            result[-1]['condition_status'] = SINGLE_VIOLATION
    return normalize_compliance(dict(run=root.name, authorization=summary['authorization'], account_delta=summary.get('account_delta'),
        groups=summarize(result), rows=result,
        limitations=['One attempt per task and condition; descriptive validation set, not a general superiority claim.',
            'Full-score counts include all selected tasks in denominator; unknown grades are reported separately.',
            'Costs are off-peak token-usage estimates plus successful-HTTP web estimates, not invoices.',
            'Usage from failed or unobserved requests is unknown; a run token does not authenticate process origin.',
            'Native lifecycle evidence does not establish substantive worker contribution.',
            'DataClaw scores use adapted per-part rubric; process metrics remain unavailable.'],
        price_source='https://api-docs.deepseek.com/quick_start/pricing/'))


def summarize(result):
    groups = []
    for b in ('dataclawbench', 'hybriddeepresearch', 'kramabench', 'fdabench', 'all'):
        for k in ('claude-code-single-agent', 'native', 'claude-code-subagents','observations','full'):
            selected = [r for r in result if r['backend'] == k and (b == 'all' or r['benchmark'] == b)]
            if not selected:
                continue
            known = [r['score'] for r in selected if r['score'] is not None]
            compliant = [0 if confirmed_single_violation(r.get('runtime_backend', r['backend']), [r],
                audit=r, accounting=dict(by_role=r.get('by_role') or {})) else
                r.get('compliant_score', r['score']) for r in selected]
            elapsed = [r['seconds'] for r in selected if r['seconds'] is not None]
            costs = [r['total_usd_offpeak'] for r in selected]
            groups.append(dict(benchmark=b, backend=k, attempts=len(selected), graded=len(known),
                infra_degraded=sum(r.get('infra_degraded') is True for r in selected),
                infra_health_unknown=sum(r.get('infra_degraded') is None for r in selected),
                upstream_5xx=sum(len(r.get('upstream_5xx', [])) for r in selected),
                raw_accuracy=sum(known)/len(selected) if len(known)==len(selected) else None,
                compliant_accuracy=sum(compliant)/len(selected) if all(v is not None for v in compliant) else None,
                protocol_accepted=sum(r.get('protocol_accepted') is True for r in selected),
                protocol_measured=sum(r.get('protocol_accepted') is not None for r in selected),
                full_score=sum(s == 1 for s in known),
                mean_score=sum(known)/len(selected) if b != 'all' and selected and len(known) == len(selected) else None,
                statuses=dict(Counter(r['status'] for r in selected)),
                mean_minutes=sum(elapsed)/len(elapsed)/60 if elapsed else None,
                time_coverage=len(elapsed), cost_coverage=sum(c is not None for c in costs),
                known_usd_offpeak_subtotal=sum(c for c in costs if c is not None),
                total_usd_offpeak=sum(costs) if all(c is not None for c in costs) else None,
                model_requests=sum(r['model_requests'] for r in selected),
                known_model_usd_offpeak_subtotal=sum(r.get('known_model_usd_offpeak_subtotal') or 0 for r in selected)
                    if any(r.get('known_model_usd_offpeak_subtotal') is not None for r in selected) else None,
                requests_with_unknown_cost=sum(r['requests_with_unknown_cost'] for r in selected)
                    if all(type(r.get('requests_with_unknown_cost')) is int for r in selected) else None,
                native_audit_passes=sum(r['native_audit_passed'] is True for r in selected)))
    return groups


def timeout_zero(report):
    revised = copy.deepcopy(report)
    for row in revised['rows']:
        if row['status'] == 'timed_out' and row['score'] is None:
            row.update(score=0.0, raw_score=0.0, compliant_score=0.0, grade_status='timeout_zero_by_user_policy')
    revised['groups'] = summarize(revised['rows'])
    revised['score_policy'] = 'Timeouts score zero; other unknown scores remain unknown.'
    revised['limitations'].append(revised['score_policy'])
    return revised


def replace_upstream_failures(original, recovery):
    """Use authorized recovery artifacts, without selecting scores or erasing costs."""
    if original.get('upstream_replacement') or recovery['authorization'].get('upstream_recovery_from') is None:
        raise ValueError('Require an original report and an explicit upstream recovery')
    auth = recovery['authorization']
    if (Path(auth['upstream_recovery_from']).name != original['run']
            or auth['protocol_settings'] != original['authorization']['protocol_settings']
            or auth['task_manifest_sha256'] != original['authorization']['task_manifest_sha256']):
        raise ValueError('Recovery source/settings/manifest differ')
    key = lambda row: (row['benchmark'], row['task_id'], row['backend'])
    primary = {key(row): row for row in original['rows']}
    eligible = {key(row) for row in auth['upstream_recovery']}
    replacements = {key(row): row for row in recovery['rows']}
    if (len(primary) != len(original['rows']) or len(replacements) != len(recovery['rows'])
            or set(replacements) != eligible or not eligible <= set(primary)
            or any(primary[k]['status'] != 'cli_error' for k in eligible)):
        raise ValueError('Recovery rows must exactly match authorized infrastructure failures')
    revised = copy.deepcopy(original)
    revised['rows'] = [copy.deepcopy(replacements.get(key(row), row)) for row in original['rows']]
    revised['groups'] = summarize(revised['rows'])
    all_attempts = original['rows'] + recovery['rows']
    operational = []
    for group in summarize(all_attempts):
        if group['benchmark'] == 'all':
            continue
        selected = [r for r in all_attempts if r['benchmark'] == group['benchmark'] and r['backend'] == group['backend']]
        operational.append({k: group[k] for k in ('benchmark', 'backend', 'attempts', 'cost_coverage',
            'known_usd_offpeak_subtotal', 'total_usd_offpeak', 'model_requests', 'time_coverage')} |
            dict(total_cli_seconds=sum(r['seconds'] for r in selected) if all(r['seconds'] is not None for r in selected) else None))
    first, second = original.get('account_delta'), recovery.get('account_delta')
    combined = ({currency: str(Decimal(first[currency]) + Decimal(second[currency])) for currency in first}
                if first is not None and second is not None and first.keys() == second.keys() else None)
    revised['account_delta'] = combined
    revised['upstream_replacement'] = dict(recovery_run=recovery['run'], replaced_count=len(eligible),
        replacements=copy.deepcopy(auth['upstream_recovery']),
        original_rows=[copy.deepcopy(row) for row in original['rows'] if key(row) in eligible],
        incurred_by_condition=operational, original_account_delta=first, recovery_account_delta=second,
        incurred_account_delta=combined, total_attempts=len(all_attempts),
        policy='Rerun replaces primary artifact regardless of score; original evidence and incurred costs retained')
    revised['limitations'] = [v for v in revised['limitations'] if not v.startswith('One attempt per task')]
    revised['limitations'].append('Primary scores/times use authorized upstream-5xx reruns, not best-of-N. Cost estimates in the main table cover effective artifacts; incurred costs include original failed attempts.')
    return revised


def write_report(report, output):
    """Export public operational metadata without copying private run artifacts."""
    report = normalize_compliance(report)
    output.mkdir(parents=True, exist_ok=False)
    columns = ['benchmark', 'task_id', 'backend', 'status', 'native_audit_passed', 'grade_status', 'score',
               'raw_score','compliant_score','protocol_accepted','condition_status',
               'seconds', 'model_requests', 'model_usd_offpeak', 'web_usd_estimate', 'judge_usd_offpeak',
               'total_usd_offpeak', 'evidence']
    with (output / 'task-results.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(report['rows'])
    (output / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    fmt = lambda value, spec='.4f': format(value, spec) if value is not None else 'unknown'
    auth = report['authorization']
    text = ['# ' + report.get('condition_label', 'Single vs Subagents'), '',
            f"Run: {report['run']}. " + ('Authorized upstream-5xx recovery artifacts replace primary results; original evidence retained.'
                if report.get('upstream_replacement') else 'One attempt per selected task and condition; no replacements.'),
            f"Effort: {auth['effort']}; solver concurrency: {auth['solver_concurrency']}; grading concurrency: {auth['judge_concurrency']}.",
            f"Protocol source: {auth.get('protocol_settings_source', 'historical authorization')}; "
            f"protocol SHA-256: {auth.get('protocol_settings_sha256') or 'not separately recorded'}.", '',
            '| Benchmark | Condition | Graded | Raw Mean | Compliant Mean | Raw Full Score | Mean Min | USD Estimate | Native Audit |',
            '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for group in report['groups']:
        if group['benchmark'] == 'all':
            continue
        count = group['attempts']
        condition = (report.get('condition_labels', {}).get(group['backend']) or
                     {'native':'Native', 'claude-code-subagents':report.get('condition_label', 'Structured'),
                      'observations':'Observation','full':'Full'}.get(group['backend']) or
                     ('Single' if group['backend'].endswith('single-agent') else report.get('condition_label', 'Subagents')))
        text.append(f"| {group['benchmark']} | {condition} | {group['graded']}/{count} | {fmt(group['mean_score'])} | "
                    f"{fmt(group['compliant_accuracy'])} | {group['full_score']}/{count} | {fmt(group['mean_minutes'], '.2f')} | "
                    f"{fmt(group['total_usd_offpeak'], '.6f')} | {group['native_audit_passes']}/{count} |")
    text += ['', '## Audit Exceptions', '']
    for row in report['rows']:
        if row['native_audit_passed'] is not True:
            text.append(f"- {row['benchmark']} / {row['task_id']} / {row['backend']}: {row['status']}; score {row['score']}.")
    if report.get('upstream_replacement'):
        recovery = report['upstream_replacement']
        text += ['', '## Upstream Recovery', '',
            f"Replaced {recovery['replaced_count']} infrastructure failures; {recovery['total_attempts']} physical attempts in total.",
            f"Shared-account interval deltas including original failures: {recovery['incurred_account_delta']}; not attributable invoices.",
            'Main-table scores/times use the recovery artifacts. Original failures are preserved and their costs are not discarded.', '',
            '| Condition | Physical Attempts | Complete Cost Records | Known USD Subtotal | Total USD | Total CLI Min |',
            '| --- | ---: | ---: | ---: | ---: | ---: |']
        for group in recovery['incurred_by_condition']:
            seconds = group['total_cli_seconds']
            text.append(f"| {group['backend']} | {group['attempts']} | {group['cost_coverage']} | "
                f"{fmt(group['known_usd_offpeak_subtotal'], '.6f')} | {fmt(group['total_usd_offpeak'], '.6f')} | "
                f"{fmt(seconds/60 if seconds is not None else None, '.2f')} |")
    text += ['', '## Limits', '', '- ' + report['compliance_policy']] + ['- ' + value for value in report['limitations']]
    (output / 'REPORT.md').write_text('\n'.join(text) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--run', type=Path)
    source.add_argument('--from-report', type=Path, help='Existing exported summary; no regrading')
    parser.add_argument('--upstream-recovery-report', type=Path,
                        help='Use authorized recovery artifacts as primary rows, retaining original costs/evidence')
    parser.add_argument('--timeout-as-zero', action='store_true')
    parser.add_argument('--condition-label', help='Explicit display label for a separately authorized study')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--report-dir', type=Path, help='Fresh directory for REPORT.md, task-results.csv and summary.json')
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Report already exists')
    if args.report_dir and (args.report_dir.exists() or (args.run and args.report_dir.resolve().is_relative_to(args.run.resolve()))):
        raise ValueError('Use a fresh report directory outside immutable run evidence')
    report = collect(args.run) if args.run else normalize_compliance(read(args.from_report))
    if args.upstream_recovery_report:
        report = replace_upstream_failures(report, read(args.upstream_recovery_report))
    if args.condition_label:
        report['condition_label'] = args.condition_label
    if args.timeout_as_zero:
        report = timeout_zero(report)
    report = normalize_compliance(report)
    if args.report_dir:
        write_report(report, args.report_dir)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report['groups'], indent=2))
