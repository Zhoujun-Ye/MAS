"""Native/Single mechanism diagnostics never call a model or inspect Structured traces."""

import json
from pathlib import Path

import pytest

from common.io import write_json
from scripts.studies.causal_experiments import audit as study


def cells(tasks=('a', 'b')):
    return [dict(round=i, seed=i, task_id=t, condition=c,
                 score=(1 if c == study.NATIVE and t == 'a' else 0),
                 native_audit_passed=True, infra_degraded=False, async_gate_race=False,
                 first_report_emitted=True, first_report_mentions_answer_artifacts=False,
                 worker_tool_inputs_mention_answer_artifacts=[])
            for i in range(3) for t in tasks for c in study.CONDITIONS]


def test_effect_clusters_tasks_not_sixty_independent_attempts():
    result = study.paired_effect(['a', 'b'], cells())
    assert result['tasks'] == 2 and result['repeats'] == 3
    assert result['mean_native_minus_single'] == .5
    assert result['task_wins'] == 1 and result['task_ties'] == 1
    assert result['exact_task_sign_flip_p'] == 1
    assert result['task_cluster_bootstrap_ci95'] == (0, 1)


def test_missing_score_is_unknown_not_dropped():
    rows = cells(); rows[0]['score'] = None
    assert study.paired_effect(['a', 'b'], rows)['status'] == 'unavailable'


def test_sensitivity_drops_whole_task_not_one_condition_or_round(monkeypatch):
    rows = cells(); rows[1]['async_gate_race'] = True
    monkeypatch.setattr(study, 'collect', lambda *a: (['a', 'b'], rows))
    result = study.audit(Path('/fixture'))
    assert result['raw']['tasks'] == 2
    assert result['protocol_clean_sensitivity']['excluded_tasks'] == ['a']
    assert result['protocol_clean_sensitivity']['effect']['tasks'] == 1
    assert result['traces']['async_gate_race_attempts'] == 1


def test_feature_reader_joins_first_call_identity_not_any_worker(tmp_path, monkeypatch):
    rows = [dict(hook_event_name='PreToolUse', tool_name='Agent', tool_use_id='first',
                 tool_input=dict(description='Inspect sources')),
            dict(hook_event_name='PostToolUse', tool_name='Agent', tool_use_id='first',
                 tool_response=dict(agentId='worker', status='async_launched')),
            dict(hook_event_name='SubagentStart', agent_id='worker', mandatory_delegation=dict(action='observed')),
            dict(hook_event_name='SubagentStop', agent_id='other', last_assistant_message='wrong donor'),
            dict(hook_event_name='PreToolUse', agent_id='worker', tool_name='Read', tool_use_id='read',
                 tool_input=dict(file_path='/workspace/submission.json')),
            dict(hook_event_name='SubagentStop', agent_id='worker', last_assistant_message='See /workspace/submission.json')]
    path = tmp_path/'native-profile/observer/events.jsonl'; path.parent.mkdir(parents=True)
    path.write_text('\n'.join(map(json.dumps, rows)))
    monkeypatch.setattr(study, 'native_subagents', lambda *a: dict(passed=True, session_end=True))
    result = study.native_features(tmp_path)
    assert result['async_gate_race'] and result['first_worker_id'] == 'worker'
    assert result['first_report_characters'] == len(rows[-1]['last_assistant_message'])
    assert result['first_report_mentions_answer_artifacts']
    assert result['worker_tool_inputs_mention_answer_artifacts'] == ['read']


def recorded_study(tmp_path, monkeypatch):
    ids = [f't{i}' for i in range(20)]
    plan = dict(task_ids=ids, rounds=[dict(name=f'round-{i}', seed=i) for i in range(3)], single_references=[])
    feature = {k:v for k,v in cells()[1].items() if k not in {'condition', 'round', 'seed', 'task_id', 'score'}}
    monkeypatch.setattr(study, 'native_features', lambda folder: feature)
    monkeypatch.setattr(study, 'infrastructure_health', lambda *a: dict(infra_degraded=False))
    for rd in plan['rounds']:
        root = tmp_path/rd['name']; rows=[]; grades=[]
        for t in ids:
            for c in study.CONDITIONS:
                out = root/'solvers'/t/c
                backend = study.SINGLE if c == study.SINGLE else 'claude-code-subagents'
                write_json(out/t/backend/'report.json', dict(single_agent_audit=dict(passed=True)))
                rows.append(dict(benchmark='kramabench', task_id=t, backend=c, run=str(out)))
                grades.append(dict(task_id=t, backend=c, grade=dict(score=0)))
        # Its path deliberately does not exist; the audit must never read it.
        rows.append(dict(benchmark='kramabench', task_id=ids[0], backend='claude-code-subagents', run='/DO-NOT-READ-STRUCTURED'))
        write_json(root/'summary.json', dict(interrupted=False, rows=rows, grades=grades))
    write_json(tmp_path/'plan.json', plan)
    return plan


def test_collect_reads_exactly_native_single_only(tmp_path, monkeypatch):
    recorded_study(tmp_path, monkeypatch)
    ids, rows = study.collect(tmp_path)
    assert len(ids) == 20 and len(rows) == 120
    assert {r['condition'] for r in rows} == set(study.CONDITIONS)


def test_collect_rejects_duplicate_cells(tmp_path, monkeypatch):
    recorded_study(tmp_path, monkeypatch)
    p = tmp_path/'round-0/summary.json'; data=json.loads(p.read_text())
    data['rows'].append(data['rows'][0]); write_json(p, data)
    with pytest.raises(ValueError, match='duplicate'):
        study.collect(tmp_path)


def test_output_cannot_overwrite_paid_evidence(tmp_path):
    with pytest.raises(ValueError, match='immutable'):
        study.main(['--run', str(tmp_path), '--output', str(tmp_path/'changed.json')])
