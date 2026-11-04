"""Merge exactly two frozen validation batches without regrading or dropping failures."""
import argparse
import csv
import json
from pathlib import Path

from benchmarks._external import digest
from benchmarks._io import write_json
from scripts.server.benchmark_matrix import BACKENDS, BENCHMARKS
from scripts.studies.matched_matrix_report import collect, summarize


def merge_rows(manifest, batches):
    if len(batches) != 2:
        raise ValueError('Require exactly the initial and extension batches')
    rows = []
    for index, batch in enumerate(batches):
        expected = {(b, t['task_id'], k) for b in BENCHMARKS
                    for t in manifest['benchmarks'][b][index * 10:(index + 1) * 10] for k in BACKENDS}
        actual = [(r['benchmark'], r['task_id'], r['backend']) for r in batch['rows']]
        if len(actual) != 60 or len(set(actual)) != 60 or set(actual) != expected:
            raise ValueError('Batch does not exactly cover its frozen slice; no missing, duplicate or replacement tasks')
        rows.extend(dict(r, batch='initial' if index == 0 else 'extension', source_batch=batch['run']) for r in batch['rows'])
    return rows


def formatted(value, spec='.4f'):
    return format(value, spec) if value is not None else 'unknown'


def report(manifest_path, initial, extension, output):
    if output.exists() or any(output.resolve().is_relative_to(p.resolve()) for p in (initial, extension)):
        raise ValueError('Use a fresh report directory outside immutable run evidence')
    manifest = json.loads(manifest_path.read_text())
    if digest(initial / 'authorization.json') != manifest['initial_authorization_sha256']:
        raise ValueError('Initial batch authorization differs from the frozen manifest')
    auth = json.loads((extension / 'authorization.json').read_text())
    if auth.get('task_manifest_sha256') != digest(manifest_path) or auth.get('task_offset') != 10:
        raise ValueError('Extension was not bound to the frozen second slice')
    batches = [collect(p) for p in (initial, extension)]
    for batch in batches:
        a = batch['authorization']
        if a['effort'] != 'high' or a['solver_concurrency'] != 6 or a['judge_concurrency'] != 2 or a['organization_override']:
            raise ValueError('Baseline configuration mismatch')
    rows = merge_rows(manifest, batches)
    result = dict(kind='validation20-baseline-v1', task_manifest_sha256=digest(manifest_path),
        source_summaries=[dict(path=str(p / 'summary.json'), sha256=digest(p / 'summary.json')) for p in (initial, extension)],
        groups=summarize(rows), rows=rows, batches=[{k: v for k, v in b.items() if k != 'rows'} for b in batches],
        limitations=batches[0]['limitations'] + [
            'This is a reusable development/validation set, not an independent held-out test.',
            'Two batches ran at different times; timing and cache conditions are not randomized.',
            'Assigned-condition summaries retain native-condition audit failures; do not claim those used subagents.'])
    output.mkdir(parents=True)
    write_json(output / 'summary.json', result)
    write_json(output / 'task-manifest.json', manifest)
    columns = ['benchmark', 'task_id', 'backend', 'batch', 'status', 'native_audit_passed', 'grade_status', 'score',
               'seconds', 'model_requests', 'model_usd_offpeak', 'web_usd_estimate', 'judge_usd_offpeak', 'total_usd_offpeak', 'evidence']
    with (output / 'task-results.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    lines = ['# Validation20 v1: Single vs Subagents', '',
             '20 fixed questions per benchmark, one attempt per condition. No retries or replacements.',
             'All conditions use Claude Code 2.1.286 / DeepSeek Flash / high, v4 default Subagents prompt.', '',
             '| Benchmark | Condition | Graded | Mean Score | Full Score | Mean Min | USD Estimate | Native Audit |',
             '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for g in result['groups']:
        if g['benchmark'] == 'all':
            continue
        condition = 'Single' if g['backend'].endswith('single-agent') else 'Subagents'
        lines.append(f"| {g['benchmark']} | {condition} | {g['graded']}/20 | {formatted(g['mean_score'])} | "
            f"{g['full_score']}/20 | {formatted(g['mean_minutes'], '.2f')} | {formatted(g['total_usd_offpeak'], '.6f')} | {g['native_audit_passes']}/20 |")
    lines += ['', '## Audit Exceptions', '']
    for row in rows:
        if row['native_audit_passed'] is not True:
            lines.append(f"- {row['benchmark']} / {row['task_id']} / {row['backend']}: {row['status']}; score {row['score']}.")
    lines += ['', '## Limits', ''] + ['- ' + value for value in result['limitations']]
    lines += ['', 'Costs include solver model, web and judge estimates, not provider invoices.',
              'Rates: https://api-docs.deepseek.com/quick_start/pricing/', '', '## Per-Task Results', '',
              '| Benchmark | Task ID | Single Score | Subagents Score | Single Min | Subagents Min |',
              '| --- | --- | ---: | ---: | ---: | ---: |']
    by_key = {(r['benchmark'], r['task_id'], r['backend']): r for r in rows}
    for b in BENCHMARKS:
        for task in manifest['benchmarks'][b]:
            a, c = [by_key[b, task['task_id'], k] for k in BACKENDS]
            minutes = lambda r: r['seconds'] / 60 if r['seconds'] is not None else None
            lines.append(f"| {b} | {task['task_id']} | {formatted(a['score'])} | {formatted(c['score'])} | "
                         f"{formatted(minutes(a), '.2f')} | {formatted(minutes(c), '.2f')} |")
    (output / 'REPORT.md').write_text('\n'.join(lines) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--initial-run', type=Path, required=True)
    parser.add_argument('--extension-run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = report(args.manifest, args.initial_run, args.extension_run, args.output)
    print(json.dumps(result['groups'], indent=2))
