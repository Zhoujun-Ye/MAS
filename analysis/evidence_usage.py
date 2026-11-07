"""Read-only trajectory audit; exports counts, never task/answer/blob payloads."""

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
import re
from pathlib import Path

from benchmarks.kramabench.evaluation import score_answer
from harness.evidence_mas.decision import DecisionProtocol
from harness.evidence_mas.store import Store


def timestamp(value):
    return datetime.fromisoformat(value).timestamp()


def merged(intervals):
    result = []
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if result and start <= result[-1][1]:
            result[-1] = (result[-1][0], max(end, result[-1][1]))
        else:
            result.append((start, end))
    return result


def duration(intervals):
    return sum(b-a for a, b in merged(intervals))


def timing(folder, report):
    start, end = timestamp(report['started_at']), timestamp(report['finished_at'])
    wall = end-start
    clip = lambda values: [(max(start,a), min(end,b)) for a,b in values if min(end,b)>max(start,a)]
    records = [json.loads(line) for line in (folder/'gateway-requests.jsonl').read_text().splitlines()]
    model = clip([(timestamp(r['dispatched_at']), timestamp(r['finished_at'])) for r in records
        if r.get('event') in {'finished','shutdown'} and r.get('route')=='/anthropic/v1/messages'
        and r.get('upstream_attempted') and r.get('dispatched_at') and r.get('finished_at')])
    events = [json.loads(line) for line in (folder/'native-profile/observer/events.jsonl').read_text().splitlines()]
    starts, bash, tool_counts, mcp_errors, sleep_commands = {}, [], Counter(), 0, 0
    for event in events:
        name, kind = event.get('tool_name'), event.get('hook_event_name')
        if kind=='PreToolUse':
            tool_counts[name] += 1
            if name=='Bash' and re.search(r'\bsleep\s',event.get('tool_input',{}).get('command','')):
                sleep_commands += 1
        if name and name.startswith('mcp__evidence') and kind in {'PostToolUse','PostToolUseFailure'}:
            response = event.get('tool_response')
            mcp_errors += kind=='PostToolUseFailure' or (isinstance(response,dict) and response.get('isError') is True)
        if name!='Bash' or not event.get('tool_use_id'):
            continue
        key = (event.get('session_id'), event.get('agent_id'), event['tool_use_id'])
        if kind=='PreToolUse':
            starts.setdefault(key, timestamp(event['observer_received_at']))
        elif kind in {'PostToolUse','PostToolUseFailure'} and key in starts:
            bash.append((starts.pop(key), timestamp(event['observer_received_at'])))
    bash = clip(bash)
    m, b, both = duration(model), duration(bash), duration(model+bash)
    return dict(cli_window_seconds=wall, model_inflight_union_seconds=m, bash_union_seconds=b,
        overlap_seconds=m+b-both, neither_seconds=max(0, wall-both), unmatched_bash_starts=len(starts),
        native_tool_counts=dict(tool_counts), sleep_commands=sleep_commands, detected_mcp_errors=mcp_errors), start


def matches(value, grade):
    if grade.get('answer_type')=='string_approximate':
        return None
    result = score_answer(value, grade['target'], grade['answer_type'],
        numeric_policy=grade['scoring_contract'].get('numeric_success_policy',{}).get('name','scale_aware_v3'))
    return result.get('score')==1


def workspace(folder, start, wall, grade):
    store = Store(folder/'native-profile/evidence', 'benchmark-evidence', readonly=True)
    with store.connect() as db:
        observations = store.latest(db, 'observation')
        events = [json.loads(row[0]) for row in db.execute('SELECT body FROM events ORDER BY seq')]
        state = DecisionProtocol(store).snapshot(db)
    by_id = {o['id']:o for o in observations}
    worker = lambda o: o.get('agent_id','unknown')!='unknown'
    counts, previews, direct_reads, decision_worker_reads = Counter(), set(), set(), 0
    first_access, views, selection_checks = None, {}, []
    for event in events:
        role, method = event['role'], event['method']
        if role=='collector':
            continue
        counts[role+'/'+method] += 1
        args, result = store.read_blob(event['arguments_ref']), store.read_blob(event['result_ref'])
        if role=='lead':
            when = timestamp(event['timestamp'])
            first_access = min(first_access,when) if first_access is not None else when
            if method in {'obs.list','obs.search'}:
                previews.update(item['id'] for item in result.get('items',[]) if item['id'] in by_id and worker(by_id[item['id']]))
            if method=='obs.read' and args.get('obs_id') in by_id and worker(by_id[args['obs_id']]):
                direct_reads.add(args['obs_id'])
            if method=='decision.view':
                views[result['snapshot']] = result
            if method=='decision.read' and args.get('candidate_id'):
                ref=result.get('observation')
                if ref is None:  # Retained v3 reads exposed only the first representative.
                    candidate = next((c for c in state['candidates'] if c['id']==args['candidate_id']),None)
                    ref=candidate['observations'][0] if candidate else None
                if ref and ref['id'] in by_id:
                    decision_worker_reads += worker(by_id[ref['id']])
            if method=='decision.select':
                view = views.get(args['snapshot'])
                candidates = view.get('candidates',[]) if view else []
                choice = next((c for c in candidates if c['id']==args['candidate_id']),None)
                selection_checks.append(dict(view_available=view is not None, candidate_count=len(candidates),
                    correct_option_available=any(matches(c['value'],grade) is True for c in candidates),
                    selected_correct=matches(choice['value'],grade) if choice else None,
                    criterion_characters=len(args.get('basis',{}).get('criterion',''))))
    candidate_values = [c['value'] for c in state['candidates']]
    intermediate = state['intermediate']
    # Extraction above is gold-blind. Reference comparison is offline coverage analysis only.
    return dict(observations=len(observations), worker_observations=sum(worker(o) for o in observations),
        method_counts=dict(counts), lead_worker_preview_observations=len(previews),
        lead_direct_worker_reads=len(direct_reads), lead_decision_worker_reads=decision_worker_reads,
        first_workspace_access_fraction=(first_access-start)/wall if first_access is not None and wall>0 else None,
        candidates=len(state['candidates']), conflict=state['conflict'],
        explicit_measurements=sum(m['confidence']=='explicit' for m in intermediate),
        possible_measurements=sum(m['confidence']=='possible' for m in intermediate),
        invalid_measurements=state['invalid_measurement_count'],
        gold_in_final_candidates=any(matches(v,grade) is True for v in candidate_values),
        gold_in_explicit_intermediates=any(matches(m['value'],grade) is True for m in intermediate if m['confidence']=='explicit'),
        gold_in_possible_hints=any(matches(m['value'],grade) is True for m in intermediate if m['confidence']=='possible'),
        selections=selection_checks, degraded=(store.root/'degraded.jsonl').exists())


def audit(report_path):
    source = json.loads(report_path.read_text())
    rows, hashes = [], {}
    for row in source['rows']:
        folder = Path(row['evidence'])
        paths = [folder/'report.json', folder/'gateway-requests.jsonl', folder/'native-profile/observer/events.jsonl']
        if row['backend']=='full':
            paths.append(folder/'native-profile/evidence/store.sqlite')
        before = {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        report = json.loads((folder/'report.json').read_text())
        intervals, start = timing(folder, report)
        item = dict(task_id=row['task_id'], condition=row['backend'], score=row['score'], timing=intervals,
                    resources=report.get('resources'), native_audit=report.get('subagents_audit',{}).get('passed'))
        if row['backend']=='full':
            item['workspace'] = workspace(folder, start, intervals['cli_window_seconds'], report['grade'])
            item['gate'] = report.get('decision_gate')
        for p in paths:
            assert hashlib.sha256(p.read_bytes()).hexdigest()==before[str(p)], p
        hashes.update(before)
        rows.append(item)
    return dict(rows=rows, input_report_sha256=hashlib.sha256(report_path.read_bytes()).hexdigest(),
        artifact_hashes=hashes, paid_calls=0, historical_code_executed=False, originals_modified=False,
        limits='Reads/previews are not comprehension or causal use. Model intervals include network/provider time; Bash time is not CPU time. Gold is post-extraction only; no new judges.')


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(result,stream,indent=2)
    print(json.dumps(dict(tasks=len(result['rows']),paid_calls=0,output=str(args.output))))
