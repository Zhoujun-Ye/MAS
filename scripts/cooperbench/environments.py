#!/usr/bin/env python3
"""Prepare the entire pinned image inventory without any model calls."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from benchmarks.cooperbench.adapter import Pair, verify_checkout, REVISION


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--registry-mirror', help='Explicit registry hostname; never changes Docker daemon configuration')
    parser.add_argument('--expected-image-ids', type=Path, help='Official image name to config digest JSON map')
    parser.add_argument('--authorized-full-inventory-pull', action='store_true', required=True)
    args = parser.parse_args()
    expected = json.loads(args.expected_image_ids.read_text()) if args.expected_image_ids else {}
    if isinstance(expected, list):
        expected = {row['image']: row['image_id'] for row in expected}
    if args.registry_mirror and (not expected or '/' in args.registry_mirror or args.registry_mirror.startswith('-')):
        raise ValueError('A mirror hostname and independently obtained official image IDs are required')
    dataset = verify_checkout()
    tasks = json.loads((dataset / 'subsets/all.json').read_text())['tasks']
    args.output.mkdir(parents=True, exist_ok=False)

    def prepare(item):
        index, task = item
        pair = Pair(task['repo'], int(task['task_id']), tuple(task['pairs'][0]))
        record = dict(repo=pair.repo, task_id=pair.task_id, image=pair.image)
        try:
            found = subprocess.run(['docker', 'image', 'inspect', pair.image], capture_output=True, text=True)
            if found.returncode:
                target = pair.image
                if args.registry_mirror:
                    if pair.image not in expected:
                        raise ValueError('No official digest for mirrored image')
                    target = args.registry_mirror + '/' + pair.image
                with (args.output / f'{index}.pull.log').open('x') as log:
                    subprocess.run(['docker', 'pull', '--platform=linux/amd64', target], stdout=log, stderr=subprocess.STDOUT,
                                   timeout=1800, check=True)
                if args.registry_mirror:
                    downloaded = json.loads(subprocess.check_output(['docker', 'image', 'inspect', target]))[0]
                    if downloaded['Id'] != expected[pair.image]:
                        raise ValueError('Mirror differs from official image digest; refusing official tag')
                    subprocess.run(['docker', 'tag', target, pair.image], check=True)
                    record['acquisition_mirror'] = args.registry_mirror
                found = subprocess.run(['docker', 'image', 'inspect', pair.image], capture_output=True, text=True, check=True)
            image = json.loads(found.stdout)[0]
            if pair.image in expected and image['Id'] != expected[pair.image]:
                raise ValueError('Installed image differs from official image digest')
            record.update(status='available', image_id=image['Id'], size_bytes=image['Size'])
        except Exception as error:
            record.update(status='error', error=str(error))
        (args.output / f'{index}.json').write_text(json.dumps(record, indent=2))
        print(json.dumps(record), flush=True)
        return record

    with ThreadPoolExecutor(max_workers=2) as pool:
        records = list(pool.map(prepare, enumerate(tasks)))
    summary = dict(revision=REVISION, phase='images_only_not_native_validation', tasks=records,
                   paid_calls=0, all_available=all(r['status'] == 'available' for r in records))
    (args.output / 'summary.json').write_text(json.dumps(summary, indent=2))
    if not summary['all_available']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
