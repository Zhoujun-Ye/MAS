"""Publish corrected 104-task snapshots with explicit, auditable replacements."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from benchmarks._io import write_json


def read_json(path):
    data = Path(path).read_bytes()
    return json.loads(data), hashlib.sha256(data).hexdigest()


def load_audit(path, backend):
    audit, digest = read_json(path)
    if audit['scoring']['version'] != 'scale_aware_answer_metrics_v3':
        raise ValueError('Only the corrected V3 answer contract may be published')
    sources = {}
    for source in audit['source_runs']:
        root = Path(source['root'])
        summary, sha = read_json(root / 'summary.json')
        if sha != source['summary_sha256']:
            raise ValueError('Original source summary changed')
        sources[str(root)] = {(r['task_id'], r['backend']): r for r in summary['rows']}
    rows = {}
    for item in audit['rows']:
        source_backend = item['backend']
        canonical_backend = 'claude-code-agent-team' if source_backend == 'claude-code' else source_backend
        if canonical_backend != backend:
            continue
        task = item['task_id']
        if task in rows:
            raise ValueError('Duplicate task in scored audit')
        source = item['source_run']
        original = sources[source][(task, source_backend)]
        grade = item['corrected_grade']
        expected = item['submission_file_sha256']
        artifact = Path(source) / task / source_backend / 'submission.json'
        actual = hashlib.sha256(artifact.read_bytes()).hexdigest() if artifact.exists() else None
        if (artifact.is_symlink() or actual != expected or grade['submission_file_sha256'] != expected
                or grade.get('scoring_contract') != audit['scoring']
                or original['grade']['submission_file_sha256'] != expected
                or grade['target'] != original['grade']['target']
                or grade['prediction'] != original['grade']['prediction']):
            raise ValueError('Corrected grade does not match its exact original artifact/reference')
        rows[task] = dict(original, backend=canonical_backend, source_backend=source_backend,
            grade=grade, original_grade=original['grade'],
            source_run=source, scored_audit_sha256=digest, replacement=None)
        rows[task].pop('effective_grade', None)
    return rows, dict(path=str(Path(path).resolve()), sha256=digest, scoring=audit['scoring'])


def replace_tasks(original, repaired):
    if not repaired or set(repaired) - original.keys():
        raise ValueError('Replacements must be a nonempty subset of the original workload')
    merged = dict(original)
    for task, row in repaired.items():
        old = original[task]
        if row['backend'] != old['backend'] or row['grade']['target'] != old['grade']['target']:
            raise ValueError('Replacement backend/reference changed')
        merged[task] = dict(row, replacement=dict(previous_source_run=old['source_run'],
            previous_score=old['grade']['score'], previous_status=old['status'],
            previous_submission_sha256=old['grade']['submission_file_sha256']))
    return merged


def visible_cost(rows):
    rows = list(rows)
    known = [r.get('accounting', {}) for r in rows
             if r.get('accounting', {}).get('estimated_usd_off_peak') is not None]
    return dict(attempts=len(rows), attempts_with_usage=len(known),
        estimated_usd_off_peak=sum(x['estimated_usd_off_peak'] for x in known) if known else None,
        estimated_usd_peak=sum(x['estimated_usd_peak'] for x in known) if known else None,
        scope='Retained-message estimate, not a bill; missing accounting is unknown, not zero')


def linked_diagnostics(rows):
    selected_roots = {r['source_run'] for r in rows}
    diagnostics, seen = [], set()
    for root in selected_roots:
        source, _ = read_json(Path(root)/'summary.json')
        plan = source.get('plan', {})
        prior = plan.get('continuation_from')
        if not prior or prior in seen or prior in selected_roots:
            continue
        previous, sha = read_json(Path(prior)/'summary.json')
        if sha != plan.get('previous_summary_sha256'):
            raise ValueError('Linked diagnostic ledger changed')
        diagnostics.extend(dict(r, source_run=prior) for r in previous['rows'])
        seen.add(prior)
    return diagnostics


def summarize(rows):
    rows = list(rows)
    binary = [r for r in rows if r['grade']['score_kind'] == 'binary']
    metrics, difficulties = {}, {}
    for row in rows:
        grade = row['grade']
        group = metrics.setdefault(grade['answer_type'], dict(metric=grade['metric'], kind=grade['score_kind'],
            attempts=0, scored=0, score_sum=0))
        group['attempts'] += 1
        if grade['score'] is not None:
            group['scored'] += 1
            group['score_sum'] += grade['score']
        if grade['score_kind'] == 'binary':
            difficulty = 'easy' if '-easy-' in row['task_id'] else 'hard'
            subset = difficulties.setdefault(difficulty, dict(attempts=0, correct=0))
            subset['attempts'] += 1
            subset['correct'] += grade['score'] == 1
    for values in metrics.values():
        values['mean'] = values['score_sum']/values['scored'] if values['scored'] else None
    seconds = [r['cli']['elapsed_seconds'] for r in rows if r.get('cli', {}).get('elapsed_seconds') is not None]
    totals = {key: sum(r.get('accounting', {}).get('observed_totals', {}).get(key, 0) for r in rows)
              for key in ('input_tokens', 'output_tokens', 'cache_hit_tokens')}
    roles = {}
    for row in rows:
        for role, usage in row.get('accounting', {}).get('by_role', {}).items():
            group = roles.setdefault(role, dict(input_tokens=0, output_tokens=0, cache_hit_tokens=0))
            for key in group:
                group[key] += usage.get(key, 0)
    binary_scored = sum(r['grade']['score'] is not None for r in binary)
    return dict(attempts=len(rows), status_counts=dict(Counter(r['status'] for r in rows)),
        replay_pass=sum(r.get('pipeline_exit_code') == 0 and r.get('pipeline_answer_matches_submission') is True for r in rows),
        binary_correct=sum(r['grade']['score'] == 1 for r in binary), binary_tasks=len(binary), binary_scored=binary_scored,
        binary_accuracy=sum(r['grade']['score'] == 1 for r in binary)/len(binary) if binary and binary_scored == len(binary) else None,
        binary_by_difficulty=difficulties, metrics=metrics, mean_cli_seconds=statistics.mean(seconds) if seconds else None,
        median_cli_seconds=statistics.median(seconds) if seconds else None, elapsed_seconds_coverage=len(seconds),
        observed_tokens=totals, observed_tokens_by_role=roles,
        token_weighted_cache_hit_rate=totals['cache_hit_tokens']/totals['input_tokens'] if totals['input_tokens'] else None,
        selected_artifact_visible_cost=visible_cost(rows))


def publish(single_audit, team_audit, repair_audit, output, expected_tasks=104, expected_repairs=5):
    single, single_source = load_audit(single_audit, 'deepagents')
    team, team_source = load_audit(team_audit, 'claude-code-agent-team')
    repairs, repair_source = load_audit(repair_audit, 'claude-code-agent-team')
    if len(single) != expected_tasks or single.keys() != team.keys() or len(repairs) != expected_repairs:
        raise ValueError('Publication must contain the full matched workload and exact replacement set')
    if not all(source['scoring'] == single_source['scoring'] for source in (team_source, repair_source)):
        raise ValueError('Cohorts use different scoring contracts')
    for row in single.values():
        policy = row.get('single_agent_audit', {})
        if (not policy.get('passed') or policy.get('subagent_starts') != 0
                or policy.get('executed_delegation_tools') != 0
                or row.get('single_agent_checkpoint_audit', {}).get('member_messages') != 0):
            raise ValueError('Single condition is missing zero-subagent evidence')
    merged = replace_tasks(team, repairs)
    diagnostics = linked_diagnostics(single.values())
    cohorts = dict(single=summarize(single.values()), team=summarize(merged.values()))
    paired = Counter()
    for task, row in single.items():
        if row['grade']['score_kind'] == 'binary':
            if row['grade']['score'] is None or merged[task]['grade']['score'] is None:
                paired['unscored'] += 1
                continue
            a, b = row['grade']['score'] == 1, merged[task]['grade']['score'] == 1
            paired['both_correct' if a and b else 'single_only' if a else 'team_only' if b else 'both_wrong'] += 1
    result = dict(scoring=single_source['scoring'], cohorts=cohorts, paired_binary=dict(paired),
        source_audits=dict(single=single_source, team_original=team_source, team_repairs=repair_source),
        replacement_task_ids=sorted(repairs), source_protocol='Single: fresh 104; Team: 99 original + 5 repair attempts',
        actual_solver_attempts=dict(single_selected=expected_tasks, team_original=expected_tasks, team_repairs=expected_repairs),
        single_prior_diagnostics_excluded=True,
        linked_single_diagnostics=[dict(task_id=r['task_id'], source_run=r['source_run'], status=r['status']) for r in diagnostics],
        single_all_attempts_visible_cost=visible_cost([*single.values(), *diagnostics]),
        team_original_statistics=summarize(team.values()),
        team_all_attempts_visible_cost=visible_cost([*team.values(), *repairs.values()]),
        rows=[*sorted(single.values(), key=lambda r:r['task_id']), *sorted(merged.values(), key=lambda r:r['task_id'])],
        new_solver_calls=0, new_judge_calls=0, original_evidence_modified=False,
        publisher_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        limitation='Team is a post-repair mixed-protocol snapshot, not a fresh 104-task run or causal architecture comparison. '
                   'Cost estimates for selected artifacts exclude superseded attempts; all-attempt Team costs include them. '
                   'Account balance intervals overlap and must not be summed as separate per-backend bills.')
    output = Path(output).resolve()
    sources = [Path(p).resolve() for p in (single_audit, team_audit, repair_audit)]
    raw_roots = {Path(r['source_run']) for r in result['rows']}
    if any(output.is_relative_to(p.parent) or p.parent.is_relative_to(output) for p in sources):
        raise ValueError('Publication must be outside scoring evidence')
    if any(output.is_relative_to(p) or p.is_relative_to(output) for p in raw_roots):
        raise ValueError('Publication must be outside raw run evidence')
    output.mkdir(parents=True, exist_ok=False)
    write_json(output/'summary.json', result)
    for name, rows in (('single', single), ('team', merged)):
        write_json(output/name/'summary.json', dict(cohort=name, statistics=cohorts[name], rows=list(rows.values())))
    write_json(output/'replacements.json', [dict(task_id=t, **merged[t]['replacement'],
        new_source_run=merged[t]['source_run'], new_score=merged[t]['grade']['score']) for t in sorted(repairs)])
    (output/'REPORT.md').write_text(markdown(result))
    return result


def formatted(value, spec):
    return format(value, spec) if value is not None else 'unknown'


def markdown(result):
    a, b = result['cohorts']['single'], result['cohorts']['team']
    lines = ['# Single / Agent Team: Corrected 104-Task Results', '', result['source_protocol'], '',
        '| Metric | Strict Single | Agent Team (5 Replacements) |', '| --- | ---: | ---: |',
        f"| Valid matching pipeline replay | {a['replay_pass']}/{a['attempts']} | {b['replay_pass']}/{b['attempts']} |",
        f"| Binary answer success | {a['binary_correct']}/{a['binary_tasks']} ({formatted(a['binary_accuracy'],'.2%')}) | "
        f"{b['binary_correct']}/{b['binary_tasks']} ({formatted(b['binary_accuracy'],'.2%')}) |",
        f"| Mean CLI seconds (selected artifacts) | {formatted(a['mean_cli_seconds'],'.1f')} | {formatted(b['mean_cli_seconds'],'.1f')} |",
        f"| Token-weighted cache reuse | {formatted(a['token_weighted_cache_hit_rate'],'.2%')} | {formatted(b['token_weighted_cache_hit_rate'],'.2%')} |", '',
        '| Answer Type | Tasks per Backend | Single Mean | Team Mean |', '| --- | ---: | ---: | ---: |']
    for kind, values in a['metrics'].items():
        other = b['metrics'][kind]
        lines.append(f"| {kind} | {values['attempts']} | {formatted(values['mean'],'.6f')} | {formatted(other['mean'],'.6f')} |")
    lines += ['', '## Difficulty (Binary Tasks Only)', '', '| Difficulty | Single Correct | Team Correct |',
              '| --- | ---: | ---: |']
    for key, values in a['binary_by_difficulty'].items():
        other = b['binary_by_difficulty'][key]
        lines.append(f"| {key} | {values['correct']}/{values['attempts']} | {other['correct']}/{other['attempts']} |")
    lines += ['', 'Single has zero native subagent starts and zero checkpoint member messages in every selected attempt.', '',
              'Replaced Team tasks: ' + ', '.join(result['replacement_task_ids']) + '.', '',
              'Paired binary outcomes: ' + json.dumps(result['paired_binary']) + '.', '',
              '## Visible-Message Cost Estimates', '',
              'Single selected 104: ' + json.dumps(a['selected_artifact_visible_cost']) + '.', '',
              'Single including linked diagnostics: ' + json.dumps(result['single_all_attempts_visible_cost']) + '.', '',
              'Team selected 104 (not total expenditure): ' + json.dumps(b['selected_artifact_visible_cost']) + '.', '',
              'Team all 109 solver attempts, including superseded attempts: '
              + json.dumps(result['team_all_attempts_visible_cost']) + '.', '',
              'The earlier Single 50-turn diagnostic is retained separately and excluded from selected-baseline costs. '
              'Semantic-judge costs are not in these solver-message estimates. No model or judge was called to publish this report.', '',
              '## Limits', '', result['limitation'], '',
              'V3 removes the absolute-epsilon loophole. Continuous means are not binary accuracy; numerical agreement does not certify scientific methodology.', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--single-audit', type=Path, required=True)
    parser.add_argument('--team-audit', type=Path, required=True)
    parser.add_argument('--repair-audit', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    value = publish(args.single_audit, args.team_audit, args.repair_audit, args.output)
    print(json.dumps(dict(cohorts=value['cohorts'], paired_binary=value['paired_binary'], replacements=value['replacement_task_ids'])))


if __name__ == '__main__':
    main()
