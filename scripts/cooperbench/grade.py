#!/usr/bin/env python3
"""Run the pinned official Docker evaluator, with no model/judge calls."""
import argparse
import json
from pathlib import Path
import sys
import subprocess

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from benchmarks.cooperbench.adapter import Pair, UPSTREAM, REVISION, verify_checkout, grade, load_submitted_patches
from benchmarks.cooperbench.native import BACKEND_VERSION


def evaluate_output(output, dataset, image_inspector=None, evaluator=None):
    manifest = json.loads((output / 'manifest.json').read_text())
    result = json.loads((output / 'result.json').read_text())
    try:
        if manifest['upstream_revision'] != REVISION:
            raise ValueError('Evaluator revision mismatch')
        patches = load_submitted_patches(output, manifest, result)
        data = manifest['pair']
        pair = Pair(data['repo'], data['task_id'], tuple(data['features']))
        if image_inspector is None:
            image = json.loads(subprocess.check_output(['docker', 'image', 'inspect', pair.image], text=True))[0]['Id']
        else:
            image = image_inspector(pair.image)
        if image != manifest['image_id']:
            raise ValueError('Official evaluator image changed since agent execution')
        sys.path.insert(0, str(UPSTREAM / 'src'))
        graded = grade(pair, patches, dataset, evaluator)
    except Exception as error:
        graded = dict(status='error', correct=None, error_type=type(error).__name__)
    graded['evaluation_snapshots'] = result.get('evaluation_snapshots', {})
    graded['backend'] = BACKEND_VERSION
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
    parser.add_argument('--authorized-local-evaluation', action='store_true', required=True)
    args = parser.parse_args()
    if (args.output / 'grade.json').exists():
        raise ValueError('Refusing to overwrite a grade')
    dataset = verify_checkout()
    graded = evaluate_output(args.output, dataset)
    with (args.output / 'grade.json').open('x') as f:
        json.dump(graded, f, indent=2)
    print(json.dumps(graded))


if __name__ == '__main__':
    main()
