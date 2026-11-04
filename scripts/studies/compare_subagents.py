"""Compare a finished native Subagents study with retained Single/Team results."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from benchmarks._io import write_json
from scripts.kramabench.results import formatted, summarize, visible_cost


def compare(baseline, subagent_run, output, expected_tasks=104):
    baseline, root, output = Path(baseline).resolve(), Path(subagent_run).resolve(), Path(output).resolve()
    if output.exists() or output.is_relative_to(root) or root.is_relative_to(output):
        raise ValueError('Comparison must use a fresh namespace outside native run evidence')
    payload = baseline.read_bytes()
    retained = json.loads(payload)
    progress = json.loads((root/'progress.json').read_text())
    native_bytes = (root/'summary.json').read_bytes()
    native = json.loads(native_bytes)
    if progress.get('stage') != 'finished' or len(native['rows']) != expected_tasks:
        raise ValueError('Subagents workload is not complete')
    if native['plan']['scoring'] != retained['scoring']:
        raise ValueError('Comparison requires the exact same scoring contract')
    tasks = {r['task_id'] for r in retained['rows'] if r['backend'] == 'deepagents'}
    teams = {r['task_id'] for r in retained['rows'] if r['backend'] == 'claude-code-agent-team'}
    if len(retained['rows']) != 2*expected_tasks or teams != tasks:
        raise ValueError('Retained baseline does not contain two matched cohorts')
    if len(tasks) != expected_tasks or {r['task_id'] for r in native['rows']} != tasks:
        raise ValueError('Subagents task set differs from the retained baseline')
    rows = []
    for original in native['rows']:
        if original['backend'] != 'claude-code-subagents':
            raise ValueError('Not a native Subagents condition')
        grade = original.get('effective_grade', original['grade'])
        path = root/original['task_id']/original['backend']/'submission.json'
        actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
        if path.is_symlink() or actual != grade['submission_file_sha256']:
            raise ValueError('Submission changed after grading')
        audit = original.get('subagents_audit', {})
        if audit.get('native_team_configs') != 0 or audit.get('teammate_idle_events') != 0:
            raise ValueError('Subagents condition lacks evidence that native Teams stayed disabled')
        row = dict(original, grade=grade, source_run=str(root), replacement=None)
        row.pop('effective_grade', None)
        rows.append(row)
    stats = summarize(rows)
    stats['native_subagents_used_cases'] = sum(r['subagents_audit']['subagent_starts'] > 0 for r in rows)
    stats['native_subagent_lifecycle_passes'] = sum(r['subagents_audit']['passed'] for r in rows)
    stats['native_subagent_starts'] = sum(r['subagents_audit']['subagent_starts'] for r in rows)
    result = dict(scoring=retained['scoring'], cohorts=dict(retained['cohorts'], subagents=stats),
        source_baseline=dict(path=str(baseline), sha256=hashlib.sha256(payload).hexdigest()),
        source_subagents=dict(path=str(root/'summary.json'), sha256=hashlib.sha256(native_bytes).hexdigest()),
        rows=retained['rows']+rows, new_solver_calls=0, new_judge_calls=0,
        subagents_solver_cost=visible_cost(rows), subagents_billing=native.get('billing'),
        subagents_judge_billing=native.get('judge_billing'),
        limitation='Native contexts/prompts differ; Team baseline is 99 original + 5 repairs. '
                   'This comparison is descriptive, not causal. Missing grades/accounting remain unknown.')
    output.mkdir(parents=True, exist_ok=False)
    write_json(output/'summary.json', result)
    lines = ['# Single / Agent Team / Subagents', '',
             '| Metric | Strict Single | Agent Team | Claude Subagents |', '| --- | ---: | ---: | ---: |']
    groups = [result['cohorts'][k] for k in ('single','team','subagents')]
    for title, field, spec in (('Binary accuracy (84 tasks)', 'binary_accuracy', '.2%'),
                               ('Mean CLI seconds', 'mean_cli_seconds', '.1f'),
                               ('Cache reuse', 'token_weighted_cache_hit_rate', '.2%')):
        lines.append('| '+title+' | '+' | '.join(formatted(g[field],spec) for g in groups)+' |')
    lines += ['', '## Answer Metrics', '', '| Type | Single | Team | Subagents |', '| --- | ---: | ---: | ---: |']
    for kind in groups[0]['metrics']:
        lines.append('| '+kind+' | '+' | '.join(formatted(g['metrics'][kind]['mean'],'.6f') for g in groups)+' |')
    lines += ['', f"Subagents observed in {stats['native_subagents_used_cases']}/{expected_tasks} cases; "
              f"native lifecycle checks passed in {stats['native_subagent_lifecycle_passes']}/{expected_tasks} cases.",
              '', 'Subagents visible-message solver estimate: '+json.dumps(result['subagents_solver_cost'])+'.',
              '', 'Subagents solver account interval: '+json.dumps(result['subagents_billing'])+'.',
              '', 'Subagents judge account interval: '+json.dumps(result['subagents_judge_billing'])+'.',
              '', result['limitation'], '']
    (output/'REPORT.md').write_text('\n'.join(lines))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--subagent-run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    value = compare(args.baseline, args.subagent_run, args.output)
    print(json.dumps(value['cohorts']))


if __name__ == '__main__':
    main()
