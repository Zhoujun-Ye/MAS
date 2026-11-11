from copy import deepcopy
import json

import pytest

from scripts.studies.compare_infra import change,complete_sum,gateway_tokens
from scripts.studies import compare_infra


def records():
    return [dict(event='dispatched',request_id='a',route='/anthropic/v1/messages'),
        dict(event='finished',request_id='a',route='/anthropic/v1/messages',upstream_attempted=True,
             outcome='response_complete',usage_status='observed',http_status=200,
             usage=dict(input_tokens=10,cache_creation_input_tokens=2,cache_read_input_tokens=100,output_tokens=8))]


def test_gateway_tokens_distinguish_cached_and_uncached_inputs():
    result=gateway_tokens(records())
    assert result['complete']
    assert result['input_tokens']==112 and result['uncached_input_tokens']==12
    assert result['cache_hit_tokens']==100 and result['output_tokens']==8


@pytest.mark.parametrize('fault',('duplicate','missing','partial','failed','missing-cache','wrong-id'))
def test_incomplete_usage_never_becomes_zero_or_complete(fault):
    rows=deepcopy(records())
    if fault=='duplicate':rows.append(dict(rows[-1]))
    elif fault=='missing':rows.pop()
    elif fault=='partial':rows[-1]['usage_status']='partial'
    elif fault=='failed':rows[-1]['http_status']=503
    elif fault=='missing-cache':rows[-1]['usage'].pop('cache_read_input_tokens')
    else:rows[-1]['request_id']='other'
    result=gateway_tokens(rows)
    assert not result['complete']
    assert result['input_tokens'] is None and result['output_tokens'] is None


def test_unknown_aggregates_and_zero_baselines_stay_explicit():
    assert complete_sum([1,None]) is None
    assert complete_sum([]) is None
    assert complete_sum([0,0])==0
    assert change(None,1)['delta'] is None
    assert change(0,1)['percent'] is None
    assert change(10,8)['percent']==-20


def test_cost_uses_uncached_inputs_and_separate_web_price(tmp_path,monkeypatch):
    (tmp_path/'report.json').write_text('{}')
    (tmp_path/'gateway-requests.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in records()))
    (tmp_path/'cli').mkdir();(tmp_path/'cli/stdout.log').write_text('')
    monkeypatch.setattr(compare_infra,'timing',lambda *a:({},0))
    monkeypatch.setattr(compare_infra,'tool_errors',lambda *a:{})
    row=dict(evidence=str(tmp_path),backend='claude-code-single-agent',seconds=1,score=1,status='cli_exited',
        by_role={},native_audit_passed=True,resources={},reconciliation='matched',
        web_usd_estimate=.00075,judge_usd_offpeak=0,total_usd_offpeak=None)
    pricing=dict(cny_per_million_offpeak=dict(cache_miss=1,cache_hit=.02,output=4),
                 web_success_usd=.00075,web_success_cny=.005)
    assert compare_infra.snapshot(row,pricing)['normalized_cny_offpeak']==pytest.approx(.005046)
    row['web_usd_estimate']=None
    assert compare_infra.snapshot(row,pricing)['normalized_cny_offpeak'] is None
    (tmp_path/'gateway-requests.jsonl').unlink()
    result=compare_infra.snapshot(row,pricing)
    assert result['tokens']['model_requests'] is None and result['tokens']['output_tokens'] is None


@pytest.mark.parametrize('fault',('task','effort','prompt','binary','scope','duplicate'))
def test_comparison_rejects_unmatched_or_changed_conditions(tmp_path,monkeypatch,fault):
    before,after=tmp_path/'before',tmp_path/'after'
    for root in (before,after):
        root.mkdir()
        (root/'task-manifest.json').write_text(json.dumps(dict(benchmarks={'fdabench':[dict(task_id='a',task_sha256='h')]})))
    row=dict(benchmark='fdabench',task_id='a',backend='claude-code-single-agent',prompt={'sha256':'same'})
    old=dict(authorization=dict(protocol_settings=dict(effort='max',cpu_per_attempt=2),
        runtime_preflight=dict(binary_sha256='same')),rows=[row])
    new=deepcopy(old);new['authorization']['protocol_settings']['cpu_per_attempt']=8
    if fault=='task':(after/'task-manifest.json').write_text('{"benchmarks":{}}')
    elif fault=='effort':new['authorization']['protocol_settings']['effort']='high'
    elif fault=='prompt':new['rows'][0]['prompt']['sha256']='changed'
    elif fault=='binary':new['authorization']['runtime_preflight']['binary_sha256']='changed'
    elif fault=='scope':new['rows'][0]['task_id']='other'
    else:new['rows'].append(dict(new['rows'][0]))
    monkeypatch.setattr(compare_infra,'collect',lambda root:old if root==before else new)
    monkeypatch.setattr(compare_infra,'snapshot',lambda *a:pytest.fail('Unmatched comparison read trajectories'))
    with pytest.raises(ValueError):compare_infra.compare(before,after,{})


def test_matched_groups_use_weighted_cache_and_preserve_score_unknowns(tmp_path,monkeypatch):
    roots=[tmp_path/'before',tmp_path/'after'];reports=[]
    for phase,root in enumerate(roots):
        root.mkdir()
        (root/'task-manifest.json').write_text('{"benchmarks":{"fdabench":["a","b"]}}')
        reports.append(dict(authorization=dict(protocol_settings=dict(effort='max',cpu_per_attempt=2 if phase==0 else 8,
            compute_threads=1 if phase==0 else 4),runtime_preflight=dict(binary_sha256='same')),
            account_delta={'CNY':str(phase+1)},rows=[dict(benchmark='fdabench',task_id=t,
                backend='claude-code-single-agent',prompt={'sha256':'same'},phase=phase,index=i)
                for i,t in enumerate(('a','b'))]))
    monkeypatch.setattr(compare_infra,'collect',lambda root:reports[roots.index(root)])
    def snapshot(row,pricing):
        total,hit=(100,90) if row['index']==0 else (900,450)
        return dict(seconds=60 if row['phase']==0 else 30,score=None if row['phase'] and row['index'] else 1,
            status='cli_exited',tokens=dict(input_tokens=total,cache_hit_tokens=hit,
                uncached_input_tokens=total-hit,output_tokens=10 if row['phase']==0 else 20,model_requests=1),
            normalized_cny_offpeak=.1,normalized_usd_offpeak=.01,native_audit_passed=True,
            pdf_renderer_failures=0,errors={'reported_tool_errors':0})
    monkeypatch.setattr(compare_infra,'snapshot',snapshot)
    group=compare_infra.compare(*roots,{})['groups'][0]
    assert group['before']['cache_hit_rate']==pytest.approx(.54)
    assert group['changes']['mean_seconds']['percent']==-50
    assert group['changes']['output_tokens']['percent']==100
    assert group['after']['full_scores']==group['after']['known_scores']==1
    assert group['attempts_per_phase']==2
