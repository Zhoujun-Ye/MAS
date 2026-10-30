#!/usr/bin/env python3
"""Authorized three-pair pilot: gate, provision, run once, grade, clean own containers."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from benchmarks.cooperbench.adapter import REVISION
from benchmarks.cooperbench.native import DockerBackend, BACKEND_VERSION, BUILD_WHEELS
from harness.config import source_digest
from harness.execution import ContainerWorkspace
from benchmarks.cooperbench.isolation import prepare_worker, ISOLATION_VERSION
from native_check import PILOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gates', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--authorized-three-paid-pairs-once', action='store_true', required=True)
    args = parser.parse_args()
    gates = json.loads((args.gates / 'summary.json').read_text())
    if (gates['revision'] != REVISION or gates['backend'] != BACKEND_VERSION
            or gates.get('worker_isolation') != ISOLATION_VERSION):
        raise ValueError('Native gate setup mismatch')
    args.output.mkdir(parents=True, exist_ok=False)
    frozen_source = source_digest()
    manifest = dict(source=frozen_source, revision=REVISION, backend=BACKEND_VERSION,
                    build_wheels=BUILD_WHEELS, pairs=[p.key for p in PILOT],
                    worker_isolation=ISOLATION_VERSION,
                    gates=str(args.gates), monetary_cap=None, attempts_per_pair=1,
                    selection='first lite pair in three preselected Python repos',
                    gate_digests={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in args.gates.glob('*.json')})
    (args.output / 'pilot-manifest.json').write_text(json.dumps(manifest, indent=2))
    records = []
    for index, pair in enumerate(PILOT):
        gate = json.loads((args.gates / f'{index}.json').read_text())
        if gate['pair'] != pair.key:
            raise ValueError('Native gate pair mismatch')
        if not gate['gate_passed']:
            records.append(dict(pair=pair.key, status='excluded_native_gate', paid_attempts=0))
            continue
        if source_digest() != frozen_source:
            raise ValueError('Source changed during pilot')
        image = json.loads(subprocess.check_output(['docker', 'image', 'inspect', pair.image], text=True))[0]['Id']
        if image != gate['image_id']:
            raise ValueError('Native gate image mismatch')
        sandboxes = []
        output = args.output / str(index)
        try:
            for _ in range(2):
                sandboxes.append(DockerBackend().create_sandbox(pair.image, timeout=1800, workdir='/workspace/repo'))
                prepare_worker(ContainerWorkspace(sandboxes[-1].container, '/workspace/repo', timeout=180))
            print(json.dumps(dict(pair=pair.key, event='paid_attempt_start')), flush=True)
            with (args.output / f'{index}.run.log').open('x') as log:
                run = subprocess.run([sys.executable, str(ROOT / 'scripts/cooperbench/run.py'),
                    '--repo', pair.repo, '--task', str(pair.task_id), '--features', *map(str, pair.features),
                    '--containers', *[s.container for s in sandboxes], '--output', str(output),
                    '--scheduler', 'async', '--authorized-one-paid-pair'], stdout=log, stderr=subprocess.STDOUT)
            with (args.output / f'{index}.grade.log').open('x') as log:
                graded = subprocess.run([sys.executable, str(ROOT / 'scripts/cooperbench/grade.py'),
                    str(output), '--authorized-local-evaluation'], stdout=log, stderr=subprocess.STDOUT)
            record = dict(pair=pair.key, paid_attempts=1, run_exit=run.returncode, grade_exit=graded.returncode)
            if (output / 'grade.json').exists():
                record['grade'] = json.loads((output / 'grade.json').read_text()).get('correct')
            records.append(record)
            print(json.dumps(record), flush=True)
            if run.returncode:
                break  # Do not spend further after an infrastructure/key/balance error.
        finally:
            for sandbox in sandboxes:
                sandbox.terminate()
            (args.output / 'pilot-progress.json').write_text(json.dumps(records, indent=2))
    (args.output / 'pilot-summary.json').write_text(json.dumps(records, indent=2))


if __name__ == '__main__':
    main()
