"""Versioned, offline numeric-score overlay for finished native CLI evidence."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from benchmarks.kramabench._io import write_json
from benchmarks.kramabench.evaluation import (NUMERIC_POLICY, UPSTREAM_NUMERIC_POLICY,
    grade_answer, number, scoring_contract)


def checked_original(saved, recomputed):
    for field in ('status', 'answer_type', 'metric', 'score_kind', 'score', 'metrics',
                  'prediction', 'target', 'submission_file_sha256'):
        if saved.get(field) != recomputed.get(field):
            raise ValueError('Original grade does not reproduce from exact artifact: ' + field)


def corrected_effective(original, base):
    effective = original.get('effective_grade')
    if base['answer_type'] != 'string_approximate' or effective is None:
        return base, False
    if (effective.get('submission_file_sha256') != base['submission_file_sha256']
            or effective.get('target') != base['target'] or effective.get('prediction') != base['prediction']
            or effective.get('status') != 'graded' or effective.get('score') not in (0, 1)):
        raise ValueError('Saved semantic verdict is not bound to this artifact/reference')
    return dict(effective, scoring_contract=base['scoring_contract'],
                semantic_verdict_reused=True), True


def numeric_diagnostics(grade):
    if grade['answer_type'] not in {'numeric_exact', 'string_exact'}:
        return None
    try:
        predicted, target = number(grade['prediction']), number(grade['target'])
    except (ValueError, TypeError, OverflowError):
        return None
    error = abs(predicted-target)
    relative = error / abs(target) if target else None
    return dict(absolute_error=error if math.isfinite(error) else None,
                relative_error=relative if relative is None or math.isfinite(relative) else None)


def rescore(upstream, runs, output):
    runs, output = [Path(p).resolve() for p in runs], Path(output).resolve()
    if any(output.is_relative_to(root) or root.is_relative_to(output) for root in runs):
        raise ValueError('Overlay must not overlap original evidence')
    if output.exists():
        raise FileExistsError('Use a fresh overlay namespace')
    contract = scoring_contract(upstream, numeric_policy=NUMERIC_POLICY)
    sources, attempts, identities = [], [], set()
    for root in runs:
        if json.loads((root / 'progress.json').read_text()).get('stage') != 'finished':
            raise ValueError('Only finished runs may be rescored')
        payload = (root / 'summary.json').read_bytes()
        summary = json.loads(payload)
        if len(summary['rows']) != summary['plan']['attempts']:
            raise ValueError('Incomplete source run; do not silently change the workload')
        sources.append(dict(root=str(root), summary_sha256=hashlib.sha256(payload).hexdigest(),
                            attempts=len(summary['rows']), paid_judge_calls=summary.get('paid_judge_calls')))
        for original in summary['rows']:
            identity = original['task_id'], original['backend']
            if identity in identities:
                raise ValueError('Duplicate task/backend across joined evidence')
            identities.add(identity)
            attempts.append((root, original))
    rows, reused, groups = [], 0, {}
    for root, original in attempts:
        task, backend = original['task_id'], original['backend']
        folder = root / task / backend
        artifact = folder / 'submission.json'
        if artifact.exists() and (artifact.is_symlink() or not artifact.is_file() or artifact.stat().st_size > 1024*1024):
            raise ValueError('Unsafe exported submission')
        submission = artifact if artifact.exists() else None
        saved = original['grade']
        version = saved.get('scoring_contract', {}).get('version')
        old_policy = ({'pinned_answer_metrics_v2': UPSTREAM_NUMERIC_POLICY,
                       'scale_aware_answer_metrics_v3': NUMERIC_POLICY}).get(version)
        if old_policy is None:
            raise ValueError('Unknown saved scoring contract: ' + str(version))
        checked_original(saved, grade_answer(upstream, task, submission, numeric_policy=old_policy))
        base = grade_answer(upstream, task, submission, numeric_policy=NUMERIC_POLICY)
        effective, semantic_reused = corrected_effective(original, base)
        reused += semantic_reused
        old_effective = original.get('effective_grade', saved)
        row = dict(task_id=task, backend=backend, source_run=str(root),
            original_grade=saved, original_effective_grade=old_effective,
            corrected_grade=effective, score_changed=old_effective.get('score') != effective.get('score'),
            numeric_diagnostics=numeric_diagnostics(effective),
            methodology_unfinished=original.get('submission', {}).get('unfinished'),
            submission_file_sha256=base['submission_file_sha256'])
        rows.append(row)
        bucket = groups.setdefault(backend, {}).setdefault(effective['answer_type'], dict(
            attempts=0, scored=0, original_score_sum=0, corrected_score_sum=0,
            score_kind=effective['score_kind'], metric=effective['metric'], changed=0))
        bucket['attempts'] += 1
        bucket['changed'] += row['score_changed']
        if effective['score'] is not None:
            bucket['scored'] += 1
            bucket['corrected_score_sum'] += effective['score']
            bucket['original_score_sum'] += old_effective['score']
    for group in groups.values():
        for bucket in group.values():
            bucket['corrected_mean'] = bucket['corrected_score_sum'] / bucket['scored'] if bucket['scored'] else None
    result = dict(scoring=contract, source_runs=sources, attempts=len(rows), backends=groups, rows=rows,
        changed=sum(r['score_changed'] for r in rows), new_judge_calls=0, reused_semantic_verdicts=reused,
        original_evidence_modified=False, rescorer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        scope='Post-hoc scale-aware numeric answer audit, not an unmodified official score, new solver run, or methodology judge')
    output.mkdir(parents=True, exist_ok=False)
    for row in rows:
        write_json(output / row['task_id'] / row['backend'] / 'grade.json', row)
    write_json(output / 'summary.json', result)
    (output / 'REPORT.md').write_text(markdown(result))
    return result


def markdown(result):
    lines = ['# Scale-Aware Answer Audit V3', '', result['scope'], '',
             f"Attempts: {result['attempts']}; changed scores: {result['changed']}; new judge calls: 0; "
             f"reused semantic verdicts: {result['reused_semantic_verdicts']}.", '',
             'Binary numeric success uses target-relative tolerance 1e-4, no absolute epsilon, and exact zero for a zero reference. '
             'Other metrics remain unchanged. Original grades, artifacts and frozen summaries are not overwritten.', '',
             '| Backend | Answer Type | Kind | Scored / Attempts | Original Score Sum | Corrected Score Sum | Corrected Mean |',
             '| --- | --- | --- | ---: | ---: | ---: | ---: |']
    for backend, group in result['backends'].items():
        for kind, values in group.items():
            mean = f"{values['corrected_mean']:.6f}" if values['corrected_mean'] is not None else 'unknown'
            lines.append(f"| {backend} | {kind} | {values['score_kind']} | {values['scored']}/{values['attempts']} | "
                         f"{values['original_score_sum']} | {values['corrected_score_sum']} | {mean} |")
    lines += ['', '## Changed Cases', '', '| Task | Backend | Prediction | Reference | Original | Corrected | Relative Error |',
              '| --- | --- | --- | --- | ---: | ---: | ---: |']
    for row in result['rows']:
        if row['score_changed']:
            grade = row['corrected_grade']
            relative = (row['numeric_diagnostics'] or {}).get('relative_error')
            formatted = f'{relative:.6%}' if relative is not None else 'undefined'
            lines.append(f"| {row['task_id']} | {row['backend']} | {grade['prediction']} | {grade['target']} | "
                         f"{row['original_effective_grade']['score']} | {grade['score']} | {formatted} |")
    lines += ['', 'This audit does not certify scientific model fidelity or pipeline methodology. '
              'A numerical match is separate from those questions. Continuous metrics are not binary accuracy.', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', type=Path, required=True)
    parser.add_argument('--runs', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    value = rescore(args.upstream, args.runs, args.output)
    print(json.dumps({k: value[k] for k in ('attempts', 'changed', 'new_judge_calls', 'reused_semantic_verdicts', 'backends')}))


if __name__ == '__main__':
    main()
