"""Read-only trajectory audit; exports counts, never task/answer/blob payloads."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from benchmarks.kramabench.evaluation import score_answer
from analysis.historical_workspace import WorkspaceReader
from analysis.timing import timestamp, timing


def matches(value, grade):
    if grade.get('answer_type')=='string_approximate':
        return None
    result = score_answer(value, grade['target'], grade['answer_type'],
        numeric_policy=grade['scoring_contract'].get('numeric_success_policy',{}).get('name','scale_aware_v3'))
    return result.get('score')==1


def workspace(folder, start, wall, grade):
    store = WorkspaceReader(folder/'native-profile/evidence')
    with store.connect() as db:
        observations = store.latest(db, 'observation')
        events = [json.loads(row[0]) for row in db.execute('SELECT body FROM events ORDER BY seq')]
        state = store.recorded_state(events)
    by_id = {o['id']:o for o in observations}
    worker = lambda o: o.get('agent_id','unknown')!='unknown'
    counts, previews, direct_reads, decision_worker_reads = Counter(), set(), set(), 0
    unattributed_reads = 0
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
                if ref is None:
                    unattributed_reads += 1  # Do not reconstruct retired v3 source-selection semantics.
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
        candidates=state['candidate_count'], conflict=state['conflict'],
        explicit_measurements=sum(m['confidence']=='explicit' for m in intermediate),
        possible_measurements=None,
        invalid_measurements=state['invalid_measurement_count'],
        gold_in_final_candidates=None,
        gold_in_recorded_candidates=any(matches(v,grade) is True for v in candidate_values) if state['complete'] else None,
        gold_in_explicit_intermediates=any(matches(m['value'],grade) is True for m in intermediate if m['confidence']=='explicit'),
        gold_in_possible_hints=None, unattributed_decision_reads=unattributed_reads,
        candidate_scope='Latest recorded decision.view pages, not reconstructed terminal candidates',
        recorded_snapshot_available=state['available'], recorded_candidates_complete=state['complete'],
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
