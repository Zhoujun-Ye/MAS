#!/usr/bin/env python3
"""Run the pinned official Docker evaluator, with no model/judge calls."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from benchmarks.cooperbench.adapter import Pair, UPSTREAM, REVISION, verify_checkout, grade, load_submitted_patches
from benchmarks.cooperbench.native import BACKEND_VERSION
from benchmarks.cooperbench.environment import resolve
from harness.config import source_digest


def evaluate_output(output, dataset, image_inspector=None, evaluator=None):
    manifest = json.loads((output / 'manifest.json').read_text())
    result = json.loads((output / 'result.json').read_text())
    try:
        if manifest['upstream_revision'] != REVISION:
            raise ValueError('Evaluator revision mismatch')
        patches = load_submitted_patches(output, manifest, result)
        data = manifest['pair']
        pair = Pair(data['repo'], data['task_id'], tuple(data['features']))
        environment = (image_inspector or resolve)(pair.image)
        if environment != manifest.get('environment') or environment['image_id'] != manifest['image_id']:
            raise ValueError('Runtime environment changed since agent execution')
        sys.path.insert(0, str(UPSTREAM / 'src'))
        graded = grade(pair, patches, dataset, evaluator)
    except Exception as error:
        graded = dict(status='error', correct=None, error_type=type(error).__name__, error=str(error))
    graded['evaluation_snapshots'] = result.get('evaluation_snapshots', {})
    graded['backend'] = BACKEND_VERSION
    graded['environment'] = manifest.get('environment')
    graded['grading_source'] = source_digest()
    graded['benchmark_inputs'] = manifest.get('benchmark_inputs', {'profile': 'official'})
    graded['code_correct'] = graded['correct']
    graded['failure_class'] = result.get('failure_class')
    if result.get('failure_class') == 'agent_failure':
        graded['correct'] = False
    graded['verification'] = ('error' if graded['status'] == 'error'
                              else 'passed' if graded['code_correct'] else 'failed')
    return graded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--grade-output', type=Path, help='New immutable grading attempt; never overwrite the old verdict')
    parser.add_argument('--authorized-local-evaluation', action='store_true', required=True)
    args = parser.parse_args()
    target = args.grade_output or args.output / 'grade.json'
    if target.exists():
        raise ValueError('Refusing to overwrite a grade')
    dataset = verify_checkout()
    graded = evaluate_output(args.output, dataset)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('x') as f:
        json.dump(graded, f, indent=2)
    print(json.dumps(graded))
    if graded['status'] == 'error':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
