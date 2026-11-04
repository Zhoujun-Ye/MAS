"""Freeze outcome-blind public validation IDs; never export questions or gold."""
import argparse
import hashlib
import json
from pathlib import Path

from benchmarks._io import write_json
from benchmarks._external import digest
from scripts.common import runtime
from scripts.common.timeouts import TIMEOUT_SECONDS_BY_BENCHMARK
from scripts.server.benchmark_matrix import BACKENDS, BENCHMARKS, selections, task_fingerprint


def freeze(root, baseline, output):
    if output.exists():
        raise ValueError("Refuse to replace a frozen validation manifest")
    authorization = json.loads((baseline / 'authorization.json').read_text())
    selected = selections(root, 20, 42)
    groups = {b: [t for bench, t in selected if bench == b] for b in BENCHMARKS}
    for benchmark, tasks in groups.items():
        for backend in BACKENDS:
            old = [r['task_id'] for r in authorization['selections']
                   if r['benchmark'] == benchmark and r['backend'] == backend]
            if old != [t.id for t in tasks[:10]]:
                raise ValueError('Initial ten do not match the retained baseline')
    if authorization['effort'] != 'high' or authorization['organization_override'] is not None:
        raise ValueError('Expected the retained high/v4 baseline')
    # Bind organization text to the actual initial plans, not only current code.
    for backend in BACKENDS:
        task = groups['kramabench'][0]
        plan = json.loads((baseline / 'solvers/kramabench' / task.id / backend / 'plan.json').read_text())
        if plan['backend_instructions'][backend] != runtime.backend_instructions(backend):
            raise ValueError('Baseline organization prompt has changed')
    manifest = dict(kind='validation20-v1', sample_seed=42,
        purpose='Reusable development/validation set, not an independent held-out final test',
        selection_policy='SHA256(seed:ID), round-robin public categories/domains; first 10 retained, next 10 appended',
        initial_batch=baseline.name, initial_authorization_sha256=digest(baseline / 'authorization.json'),
        baseline_settings=dict(effort='high', organization_sha256={k: hashlib.sha256(runtime.backend_instructions(k).encode()).hexdigest() for k in BACKENDS},
            timeout_seconds_by_benchmark=dict(TIMEOUT_SECONDS_BY_BENCHMARK), solver_concurrency=6, judge_concurrency=2),
        benchmarks={b: [dict(task_id=t.id, task_sha256=task_fingerprint(b, t),
                            stratum=getattr(t, 'category', getattr(t, 'domain', None)),
                            batch='initial' if i < 10 else 'extension')
                       for i, t in enumerate(tasks)] for b, tasks in groups.items()})
    write_json(output, manifest)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--baseline-run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    manifest = freeze(args.root, args.baseline_run, args.output)
    print(json.dumps(dict(kind=manifest['kind'], tasks_by_benchmark={b: len(v) for b, v in manifest['benchmarks'].items()})))
