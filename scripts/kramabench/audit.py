"""Read-only engineering audit of question-parallel pilot evidence, without regrading."""

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from harness.runner import write_json
from harness.trace import read_trace, validate


def read(path):
    return json.loads(path.read_text())


def artifact_errors(submission, native, binding):
    code = submission.get('pipeline_code')
    if not isinstance(code, str) or not code:
        return ['No exported pipeline code']
    errors = []
    if native.get('code') != code:
        errors.append('Native response differs from exported submission')
    if hashlib.sha256(code.encode('utf-8')).hexdigest() != binding.get('pipeline_code_sha256'):
        errors.append('Exported code differs from frozen binding hash')
    return errors


def checkpoint_audit(events):
    paused, checkpoints, resumes, violations = {}, [], [], []
    calls, first_submit = 0, None
    for event in events:
        kind = event['type']
        if kind == 'llm_attempt':
            calls += 1
            if event['agent'] in paused:
                violations.append(dict(t=event['t'], agent=event['agent'], reason='model_call_while_checkpointed'))
        elif kind == 'team_checkpoint':
            worker = event['worker_id']
            if worker in paused:
                violations.append(dict(t=event['t'], agent=worker, reason='duplicate_checkpoint'))
            paused[worker] = event
            checkpoints.append(event)
        elif kind == 'team_checkpoint_resume':
            if event['agent'] not in paused:
                violations.append(dict(t=event['t'], agent=event['agent'], reason='resume_without_checkpoint'))
            paused.pop(event['agent'], None)
            resumes.append(event)
        elif kind == 'team_task' and event.get('event') == 'cancel':
            owner = event['task']['owner']
            if owner in paused and paused[owner]['cause'] == 'assignment' and paused[owner]['task_id'] == event['task']['task_id']:
                paused.pop(owner)
        elif kind == 'team_draining':
            paused.clear()
        elif kind == 'team_activation_end':
            paused.pop(event['agent_id'], None)
        elif kind == 'tool_call' and event.get('tool') == 'submit' and not event.get('error') and first_submit is None:
            first_submit = calls
    return dict(count=len(checkpoints), resumed=len(resumes), violations=violations,
                events=[{k: e.get(k) for k in ('t', 'worker_id', 'activation', 'cause', 'task_id',
                    'summary', 'slice_model_calls', 'budget')} for e in checkpoints],
                decisions=[{k: e.get(k) for k in ('t', 'agent', 'activation', 'instruction')} for e in resumes],
                first_valid_submit_model_call=first_submit,
                submitted_within_128=first_submit is not None and first_submit <= 128)


def audit(roots):
    rows, roles, errors, stamps = [], {}, Counter(), []
    for root in roots:
        for report_path in sorted(root.glob('*/*/report.json')):
            directory = report_path.parent
            report = read(report_path)
            manifest = read(directory / 'manifest.json')
            submission = read(directory / 'submission.json') if (directory / 'submission.json').exists() else {}
            native = read(directory / 'native_response.json') if (directory / 'native_response.json').exists() else {}
            grade_path = directory / 'grade.json'
            grade = read(grade_path) if grade_path.exists() else {}
            semantic = root / 'semantic-grades' / directory.parent.name / directory.name / 'grade.json'
            if semantic.exists():
                if grade.get('status') != 'pending_judge':
                    raise ValueError('Semantic overlay may only replace a pending judge grade')
                judged = read(semantic)
                if judged.get('submission_file_sha256') != grade.get('submission_file_sha256'):
                    raise ValueError('Semantic grade differs from original submission binding')
                grade = judged
            events = read_trace(directory / 'trace.jsonl')
            stamps.extend(datetime.fromisoformat(e['ts']) for e in events if e['type'] in {'run_start', 'run_end'})
            tool_errors = [e for e in events if e['type'] == 'tool_call' and e.get('error')]
            error_counts = Counter(e.get('error_kind', 'unspecified') for e in tool_errors)
            errors.update(error_counts)
            binding_errors = artifact_errors(submission, native, report.get('artifact_binding') or {})
            if grade.get('submission_file_sha256') and grade['submission_file_sha256'] != hashlib.sha256((directory / 'submission.json').read_bytes()).hexdigest():
                binding_errors.append('Grade is not bound to the exact submission file')
            arm = directory.name
            for group in report['cache']['groups']:
                if group['role'] == 'all':
                    continue
                bucket = roles.setdefault(arm, {}).setdefault(group['role'], Counter())
                for key in ('calls', 'prompt_tokens', 'cache_hit_tokens'):
                    bucket[key] += group[key]
            total = report['usage']['total']
            activations = report.get('activation_usage', {})
            rows.append(dict(task=directory.parent.name, arm=arm, path=str(directory),
                status=report['status'], source_digest=manifest['source_digest'],
                score=grade.get('score'), grading_status=grade.get('status', 'recorded' if grade else 'not_recorded'),
                answer_type=grade.get('answer_type'), metric=grade.get('metric'),
                score_kind=grade.get('score_kind', 'binary'), metrics=grade.get('metrics', {}),
                answer=submission.get('answer'), target=grade.get('target'),
                structured_answer=isinstance(submission.get('answer'), dict),
                usage=total, cost_usd_estimate=report.get('cost_usd_estimate'),
                cost_usd_actual=report.get('cost_usd_actual'), runtime_seconds=report['runtime'],
                limit_events=report['budget']['limit_events'],
                infra_affected=report['infra_affected'], trace_errors=validate(events),
                artifact_errors=binding_errors, tool_error_counts=dict(error_counts),
                tool_errors=[{k: e.get(k) for k in ('t', 'agent', 'tool', 'error_kind', 'observation')} for e in tool_errors],
                llm_errors=[{k: e.get(k) for k in ('t', 'agent', 'error_kind', 'error')} for e in events if e['type'] == 'llm_error'],
                activation_by_cause=activations.get('by_cause'),
                checkpoints=checkpoint_audit(events),
                leader_domain_tool_calls=activations.get('leader_domain_tool_calls'),
                assignment_claims=dict(Counter(e.get('completion_status') for e in activations.get('activations', []) if e['cause'] == 'assignment')),
                communication={k: report['communication'].get(k) for k in ('peer_routes', 'peer_exposed')}))
    for groups in roles.values():
        for role, bucket in groups.items():
            groups[role] = dict(bucket, hit_rate=bucket['cache_hit_tokens'] / bucket['prompt_tokens'] if bucket['prompt_tokens'] else None)
    arms = {}
    for arm in sorted({r['arm'] for r in rows}):
        selected = [r for r in rows if r['arm'] == arm]
        usage = {key: sum(r['usage'][key] for r in selected) for key in
                 ('attempted_calls', 'failed_calls', 'prompt_tokens', 'completion_tokens', 'cache_hit_tokens', 'cache_miss_tokens')}
        metric_groups = {}
        for row in selected:
            for metric, value in row['metrics'].items():
                if value is not None:
                    metric_groups.setdefault(row['answer_type'], {}).setdefault(metric, []).append(value)
        metric_groups = {kind: {name: dict(graded=len(values), mean=sum(values)/len(values))
                        for name, values in metrics.items()} for kind, metrics in metric_groups.items()}
        arms[arm] = dict(attempts=len(selected), graded=sum(r['score'] is not None for r in selected),
            binary_graded=sum(r['score'] is not None and r['score_kind'] == 'binary' for r in selected),
            continuous_graded=sum(r['score'] is not None and r['score_kind'] == 'continuous' for r in selected),
            pending_judge=sum(r['grading_status'] == 'pending_judge' for r in selected), metric_groups=metric_groups,
            passed=sum(r['score'] == 1 and r['score_kind'] == 'binary' for r in selected), structured_answers=sum(r['structured_answer'] for r in selected),
            model_limit_attempts=sum(any(e['reason'] == 'session_model_limit' for e in r['limit_events']) for r in selected),
            usage=usage, max_prompt_tokens=max(r['usage']['max_prompt_tokens'] for r in selected),
            cost_usd_estimate=sum(r['cost_usd_estimate'] or 0 for r in selected))
    return dict(attempts=len(rows), rows=rows, arms=arms, role_cache=roles, tool_errors=dict(errors),
        source_digests=sorted({r['source_digest'] for r in rows}),
        elapsed_span_seconds=(max(stamps) - min(stamps)).total_seconds() if stamps else None,
        cost_usd_estimate=sum(r['cost_usd_estimate'] or 0 for r in rows), cost_usd_actual=None,
        cost_scope='Frozen configured price-table estimate; concurrent account deltas are not additive attributable costs',
        pipeline_reexecuted=False, grading_scope='Original grade files only; missing grades are not failures or imputed scores')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=Path, nargs='+', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Refusing to overwrite existing audit evidence')
    result = audit(args.runs)
    write_json(args.output, result)
    print(json.dumps({k: result[k] for k in ('attempts', 'arms', 'cost_usd_estimate', 'source_digests')}, indent=2))
