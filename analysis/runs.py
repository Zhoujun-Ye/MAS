"""Read immutable per-run manifests, outcomes, grades and accounting records."""
import json
import hashlib
from pathlib import Path

from .legacy_trace import read_trace, usage_summary, tool_counts


def digest(value):
    canonical = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def run_directories(output):
    output = Path(output)
    return [output] if (output / 'manifest.json').exists() else sorted(p.parent for p in output.rglob('manifest.json'))


def load_runs(output, audits=None):
    runs, traces = [], {}
    for folder in run_directories(output):
        manifest = json.loads((folder / 'manifest.json').read_text())
        events = read_trace(folder / 'trace.jsonl') if (folder / 'trace.jsonl').exists() else []
        if not any(e['type'] == 'run_start' for e in events):
            continue  # Prepared but never started is not an attempt.
        run_id = str(folder.resolve())
        def read(name, default):
            path = folder / name
            return json.loads(path.read_text()) if path.exists() else default
        run = read('result.json', dict(status='unresolved', failure_class=None))
        grade = read('grade.json', {})
        accounting = read('accounting.json', {})
        trace_sha = hashlib.sha256((folder / 'trace.jsonl').read_bytes()).hexdigest()
        audit = (audits or {}).get(trace_sha, dict(status='not_audited'))
        if audit.get('status') not in ('not_audited', 'admissible', 'contaminated', 'uncontrolled_environment'):
            raise ValueError('Unknown research audit status')
        failure = run.get('failure_class')
        success = False if failure == 'agent_failure' else grade.get('correct')
        if failure in ('infrastructure_error', 'external_interruption'):
            success = None
        condition = manifest['scheduler'] + ':' + digest({k: manifest.get(k) for k in
            ('communication_policy', 'model', 'limits', 'member_limits', 'source', 'submission_contract',
             'workspace_isolation', 'tool_output_limit', 'snapshot_output_limit')})
        run.update(run_id=run_id, condition=condition, success=success, grade=grade,
                   usage=usage_summary(events), tool_counts=tool_counts(events),
                   cost_usd_estimate=accounting.get('cost_usd_estimate'),
                   account_balance_delta=accounting.get('account_balance_delta'),
                   evaluator_error=grade.get('status') == 'error', manifest=manifest,
                   trace_sha256=trace_sha, research_audit=audit)
        traces[run_id] = events
        runs.append(run)
    return runs, traces
