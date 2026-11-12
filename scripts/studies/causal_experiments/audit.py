"""Read frozen Native/Single traces and task-paired effects without model calls."""

import argparse
from collections import Counter
from itertools import product
import hashlib
import json
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from analysis.native_evidence import native_subagents
from analysis.stats import bootstrap_ci
from common.io import read_json, write_json
from harness.runtime_support.admission import infrastructure_health
from scripts.studies.krama_repeats import finite_score

SINGLE = 'claude-code-single-agent'
NATIVE = 'native'
CONDITIONS = (SINGLE, NATIVE)


def hook_rows(folder):
    path = folder/'native-profile/observer/events.jsonl'
    return [json.loads(line) for line in path.read_text().splitlines()]


def root_event(row):
    return not (row.get('agent_id') or row.get('agentId')
                or '/subagents/' in str(row.get('transcript_path', '')))


def native_features(folder):
    rows = hook_rows(folder)
    calls = [r for r in rows if root_event(r) and r.get('hook_event_name') == 'PreToolUse'
             and r.get('tool_name') in {'Agent', 'Task'}]
    returned = {}
    races = set()
    for row in rows:
        response = row.get('tool_response')
        if (root_event(row) and row.get('hook_event_name') == 'PostToolUse'
                and row.get('tool_name') in {'Agent', 'Task'} and isinstance(response, dict)):
            returned[response.get('agentId') or response.get('agent_id')] = row
        if (row.get('hook_event_name') == 'SubagentStart'
                and row.get('mandatory_delegation', {}).get('action') == 'observed'):
            prior = returned.get(row.get('agent_id'))
            if prior and prior['tool_response'].get('status') == 'async_launched':
                races.add(row['agent_id'])
    first_call = calls[0] if calls else {}
    first_return = next((r for r in rows if root_event(r) and r.get('hook_event_name') == 'PostToolUse'
        and r.get('tool_name') in {'Agent', 'Task'} and r.get('tool_use_id') == first_call.get('tool_use_id')), {})
    response = first_return.get('tool_response') or {}
    identity = (response.get('agentId') or response.get('agent_id')) if isinstance(response, dict) else None
    stop = next((r for r in rows if identity and r.get('hook_event_name') == 'SubagentStop'
                 and r.get('agent_id') == identity), {})
    text = stop.get('last_assistant_message')
    emitted = isinstance(text, str) and bool(text.strip())
    worker_calls = [r for r in rows if identity and r.get('agent_id') == identity
                    and r.get('hook_event_name') == 'PreToolUse']
    workspace_mentions = [r.get('tool_use_id') for r in worker_calls
        if any(name in json.dumps(r.get('tool_input', {})) for name in ('submission.json', 'pipeline.py'))]
    audit = native_subagents(folder)
    policy = audit.get('mandatory_delegation') or {}
    inputs = first_call.get('tool_input') or {}
    return dict(first_worker_id=identity, lead_delegation_calls=len(calls),
        first_worker_description=inputs.get('description'),
        first_worker_tools=dict(Counter(r.get('tool_name') for r in worker_calls)),
        first_report_emitted=emitted, first_report_characters=len(text) if emitted else 0,
        first_report_sha256=hashlib.sha256(text.encode()).hexdigest() if emitted else None,
        first_report_mentions_answer_artifacts=bool(emitted and any(
            name in text for name in ('/workspace/submission.json', '/workspace/pipeline.py'))),
        worker_tool_inputs_mention_answer_artifacts=workspace_mentions,
        async_gate_race=bool(races), async_gate_race_worker_ids=sorted(races),
        denied_lead_calls=policy.get('denied_tool_calls'), blocked_stops=policy.get('blocked_stops'),
        native_audit_passed=audit['passed'], session_end=audit['session_end'],
        scope='Recorded tool requests/report emissions, not semantic contribution or lead incorporation')


def collect(run):
    plan = read_json(run/'plan.json')
    if not plan or len(plan.get('rounds', [])) != 3:
        raise ValueError('Require the frozen three-round study plan')
    ids = plan['task_ids']
    if len(ids) != 20 or len(set(ids)) != 20:
        raise ValueError('Require exactly the frozen twenty task IDs')
    rows = []
    for index, rd in enumerate(plan['rounds']):
        folder = run/rd['name']
        summary = read_json(folder/'summary.json')
        if not summary or summary.get('interrupted') is not False:
            raise ValueError('Require three completed, non-interrupted round summaries')
        grades = {(g['task_id'], g['backend']): g for g in summary['grades']}
        selected = [r for r in summary['rows'] if r['backend'] in CONDITIONS]
        for item in selected:
            if item['benchmark'] != 'kramabench' or item['task_id'] not in ids:
                raise ValueError('Unexpected task in Native/Single comparison')
            condition, task = item['backend'], item['task_id']
            backend = SINGLE if condition == SINGLE else 'claude-code-subagents'
            evidence = Path(item['run'])/task/backend
            report = read_json(evidence/'report.json')
            score = (grades.get((task, condition), {}).get('grade') or {}).get('score')
            row = dict(round=index, seed=rd['seed'], task_id=task, condition=condition, score=score,
                evidence=str(evidence), reused=False,
                native_audit_passed=report.get('single_agent_audit', {}).get('passed'),
                **infrastructure_health(evidence/'gateway-requests.jsonl'))
            if condition == NATIVE:
                row.update(native_features(evidence))
            rows.append(row)
        references = plan.get('single_references', [])
        if index < len(references):
            for old in references[index]['rows']:
                if old['backend'] != SINGLE or old['benchmark'] != 'kramabench' or old['task_id'] not in ids:
                    raise ValueError('Unexpected retained Single cell')
                evidence = Path(old['evidence'])
                rows.append(dict(round=index, seed=rd['seed'], task_id=old['task_id'], condition=SINGLE,
                    score=old['score'], evidence=str(evidence), reused=True,
                    native_audit_passed=old['native_audit_passed'],
                    **infrastructure_health(evidence/'gateway-requests.jsonl')))
    expected = {(i, t, c) for i in range(3) for t in ids for c in CONDITIONS}
    observed = [(r['round'], r['task_id'], r['condition']) for r in rows]
    if len(observed) != len(set(observed)) or set(observed) != expected:
        raise ValueError('Missing, duplicate or unexpected Native/Single cells')
    return ids, rows


def paired_effect(ids, rows):
    by_cell = {(r['round'], r['task_id'], r['condition']): r for r in rows}
    groups, differences = [], []
    for condition in CONDITIONS:
        values = [[by_cell[(i, t, condition)]['score'] for t in ids] for i in range(3)]
        means = [statistics.mean(v) if v and all(finite_score(s) for s in v) else None for v in values]
        groups.append(dict(condition=condition, round_means=means,
            mean=statistics.mean(means) if all(v is not None for v in means) else None))
    for task in ids:
        values = [by_cell[(i, task, c)]['score'] for i in range(3) for c in CONDITIONS]
        if not all(finite_score(s) for s in values):
            return dict(status='unavailable', groups=groups, reason='Unknown scores are not dropped or imputed')
        differences.append(statistics.mean(by_cell[(i, task, NATIVE)]['score']
            - by_cell[(i, task, SINGLE)]['score'] for i in range(3)))
    if not differences:
        return dict(status='unavailable', groups=groups, reason='No shared tasks')
    nonzero = [d for d in differences if abs(d) > 1e-12]
    observed = abs(sum(nonzero))
    extreme = sum(abs(sum(s*d for s,d in zip(signs, nonzero))) >= observed-1e-12
                  for signs in product((-1, 1), repeat=len(nonzero)))
    return dict(status='available', groups=groups, tasks=len(ids), repeats=3,
        mean_native_minus_single=statistics.mean(differences),
        task_cluster_bootstrap_ci95=bootstrap_ci(differences, samples=20000, seed=0),
        exact_task_sign_flip_p=extreme/(2**len(nonzero)),
        task_wins=sum(d > 1e-12 for d in differences), task_losses=sum(d < -1e-12 for d in differences),
        task_ties=sum(abs(d) <= 1e-12 for d in differences),
        per_task=[dict(task_id=t, mean_difference=d) for t,d in zip(ids, differences)],
        inference_scope='Descriptive task-paired uncertainty; reused/noncontemporaneous controls and harness races prevent causal identification')


def audit(run):
    ids, rows = collect(run)
    excluded = [t for t in ids if any(r['task_id'] == t and (
        r['native_audit_passed'] is not True or r.get('async_gate_race') or r['infra_degraded'] is not False)
        for r in rows)]
    native = [r for r in rows if r['condition'] == NATIVE]
    return dict(run=str(run), conditions=list(CONDITIONS), paid_calls=0,
        raw=paired_effect(ids, rows),
        protocol_clean_sensitivity=dict(excluded_tasks=excluded,
            effect=paired_effect([t for t in ids if t not in excluded], rows),
            policy='Diagnostic only: exclude the whole task across both conditions/all rounds for audit, race or infrastructure issues; retain raw scores'),
        traces=dict(native_attempts=len(native), async_gate_race_attempts=sum(r['async_gate_race'] for r in native),
            first_reports_emitted=sum(r['first_report_emitted'] for r in native),
            first_reports_mention_answer_artifacts=sum(r['first_report_mentions_answer_artifacts'] for r in native),
            worker_inputs_mention_answer_artifacts=sum(bool(r['worker_tool_inputs_mention_answer_artifacts']) for r in native),
            interpretation='Artifact references flag manual review, not automatic proof of answer contamination'),
        rows=rows,
        limitations=['No Structured traces are analyzed.',
            'Twenty task clusters, not sixty independent tasks; dispatch seeds do not fix provider sampling.',
            'A returned worker report may contain derived answers, errors or feedback from the lead workspace.',
            'Observation and correlation do not identify which mechanism caused an answer gain.'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists() or args.output.resolve().is_relative_to(args.run.resolve()):
        raise ValueError('Use fresh output outside immutable paid evidence')
    result = audit(args.run.resolve())
    write_json(args.output, result)
    print(json.dumps({key: value for key,value in result.items() if key != 'rows'}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
