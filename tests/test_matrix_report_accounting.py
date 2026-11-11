import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.studies import matched_matrix_report
from scripts.studies.matched_matrix_report import collect, price, summarize


def report_for(tmp_path, ledger):
    output = tmp_path / 'attempt'
    folder = output / 'task' / 'claude-code-subagents'
    folder.mkdir(parents=True)
    (folder / 'gateway-requests.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in ledger))
    (tmp_path / 'summary.json').write_text(json.dumps(dict(rows=[dict(
        benchmark='dataclawbench', task_id='task', backend='claude-code-subagents',
        run=str(output), status='cli_exited')], grades=[], authorization={})))
    return collect(tmp_path)['rows'][0]


def request_pair():
    common = dict(request_id='paid-1', route='/anthropic/v1/messages', upstream_attempted=True)
    sent = dict(common, event='dispatched')
    done = dict(common, event='finished', outcome='response_complete', usage_status='observed',
                http_status=200, usage=dict(input_tokens=100, output_tokens=10))
    return sent, done


def test_local_rejection_is_not_a_paid_model_response(tmp_path):
    sent, done = request_pair()
    rejected = dict(request_id='local-1', route='/anthropic/v1/messages', event='finished',
                    upstream_attempted=False, outcome='rejected', http_status=400, usage_status='unknown')
    row = report_for(tmp_path, [sent, done, rejected])
    assert row['model_requests'] == row['model_responses'] == 1
    assert row['model_usd_offpeak'] == price(done['usage'])


def test_web_cost_uses_receipt_estimates_and_unknown_completions(tmp_path):
    sent,done=request_pair()
    web=dict(request_id='web',route='/v1/tools/fetch',upstream_attempted=True,event='dispatched')
    complete=dict(web,event='finished',web_backend='host-http',estimated_cost_usd=0,http_status=200)
    assert report_for(tmp_path/'zero',[sent,done,web,complete])['web_usd_estimate']==0
    complete.update(web_backend='deepseek',estimated_cost_usd=.00075)
    assert report_for(tmp_path/'paid',[sent,done,web,complete])['web_usd_estimate']==.00075
    complete['estimated_cost_usd']=None
    assert report_for(tmp_path/'unknown',[sent,done,web,complete])['web_usd_estimate'] is None


@pytest.mark.parametrize('change', ['partial', 'wrong-id', 'duplicate', 'missing', 'upstream-rejected'])
def test_incomplete_or_unmatched_usage_remains_unknown(tmp_path, change):
    sent, done = request_pair()
    ledger = [sent, done]
    if change == 'partial':
        done.update(outcome='client_disconnected', usage_status='partial')
        done['usage']['output_tokens'] = 0
    elif change == 'wrong-id':
        done['request_id'] = 'different-request'
    elif change == 'duplicate':
        ledger.append(dict(done))
    elif change == 'missing':
        ledger.pop()
    else:
        done.update(outcome='upstream_rejected', http_status=500)
    row = report_for(tmp_path, ledger)
    assert row['model_usd_offpeak'] is None
    assert row['total_usd_offpeak'] is None


def test_summary_has_no_empty_conditions_and_distinguishes_partial_costs():
    row = dict(benchmark='dataclawbench', backend='claude-code-subagents', score=1,
               seconds=60, total_usd_offpeak=0.1, status='cli_exited', model_requests=1,
               native_audit_passed=True)
    groups = summarize([row, dict(row, total_usd_offpeak=None)])
    assert len(groups) == 2
    assert all(g['backend'] == 'claude-code-subagents' for g in groups)
    for group in groups:
        assert group['attempts'] == 2 and group['cost_coverage'] == 1
        assert group['total_usd_offpeak'] is None
        assert group['known_usd_offpeak_subtotal'] == pytest.approx(0.1)
    assert summarize([]) == []


def test_fdabench_is_included_in_benchmark_summary():
    row=dict(benchmark='fdabench',backend='claude-code-single-agent',score=1,
        seconds=60,total_usd_offpeak=.01,status='cli_exited',model_requests=1,native_audit_passed=True)
    groups=summarize([row])
    assert [g['benchmark'] for g in groups]==['fdabench','all']
    assert groups[0]['raw_accuracy']==1


def test_report_script_keeps_direct_execution_from_an_unrelated_cwd(tmp_path):
    result = subprocess.run([sys.executable, '-I', str(Path(matched_matrix_report.__file__).resolve()),
        '--help'], cwd=tmp_path, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert '--from-report' in result.stdout
