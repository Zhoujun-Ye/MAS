#!/usr/bin/env python3
"""Verify selected base/gold tasks in isolated local Docker, without any model."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from benchmarks.cooperbench.adapter import Pair, verify_checkout, REVISION
from benchmarks.cooperbench.native import load_evaluator, BACKEND_VERSION
from benchmarks.cooperbench.isolation import prepare_worker, ISOLATION_VERSION
from harness.execution import ContainerWorkspace


PILOT = [Pair('pallets_click_task', 2068, (1, 4)),
         Pair('pallets_jinja_task', 1465, (1, 7)),
         Pair('samuelcolvin_dirty_equals_task', 43, (2, 3))]


def check(pair, dataset, module):
    image = json.loads(subprocess.check_output(['docker', 'image', 'inspect', pair.image], text=True))[0]['Id']
    task = dataset / pair.repo / f'task{pair.task_id}'
    worker = module.get_backend('docker').create_sandbox(pair.image, timeout=600, workdir='/workspace/repo')
    try:
        isolation = prepare_worker(ContainerWorkspace(worker.container, '/workspace/repo', timeout=180))
    finally:
        worker.terminate()
    rows = []
    for feature in pair.features:
        sb = module.get_backend('docker').create_sandbox(pair.image, timeout=600)
        try:
            base = sb.exec('git', '-C', '/workspace/repo', 'rev-parse', 'HEAD').stdout_read().strip()
            module._write_patch(sb, 'tests.patch', (task / f'feature{feature}/tests.patch').read_text())
            baseline = module._run_tests(sb, 'tests.patch', '', base)
        finally:
            sb.terminate()
        gold = module.run_patch_test(pair.repo, pair.task_id, feature,
                                    agent_patch=task / f'feature{feature}/feature.patch', dataset_dir=dataset)
        passed = baseline['tests_failed'] > 0 and gold['passed'] and not gold.get('error')
        rows.append(dict(feature=feature, baseline=baseline, gold=gold, gate_passed=passed))
    combined = task / 'combined.patch'
    joint = (module.test_merged(pair.repo, pair.task_id, *pair.features, patch1=combined, patch2=combined,
                               dataset_dir=dataset) if combined.exists() else
             module.test_merged(pair.repo, pair.task_id, *pair.features,
                                patch1=task / f'feature{pair.features[0]}/feature.patch',
                                patch2=task / f'feature{pair.features[1]}/feature.patch', dataset_dir=dataset))
    return dict(pair=pair.key, image_id=image, worker_isolation=isolation, features=rows, gold_joint=joint,
                gate_passed=all(r['gate_passed'] for r in rows) and joint.get('both_passed') is True and not joint.get('error'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--authorized-local-evaluation', action='store_true', required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    dataset = verify_checkout()
    module = load_evaluator()
    results = []
    for index, pair in enumerate(PILOT):
        try:
            result = check(pair, dataset, module)
        except Exception as error:
            result = dict(pair=pair.key, gate_passed=False, error_type=type(error).__name__, error=str(error))
        (args.output / f'{index}.json').write_text(json.dumps(result, indent=2))
        results.append(dict(pair=pair.key, gate_passed=result['gate_passed']))
        print(json.dumps(results[-1]), flush=True)
    summary = dict(revision=REVISION, backend=BACKEND_VERSION, worker_isolation=ISOLATION_VERSION, results=results,
                   paid_calls=0, all_passed=all(r['gate_passed'] for r in results))
    (args.output / 'summary.json').write_text(json.dumps(summary, indent=2))
    if not summary['all_passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
