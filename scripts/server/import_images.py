#!/usr/bin/env python3
"""Transfer official amd64 images through the host when server registry DNS fails.

No Docker daemon/DNS changes and no credentials or host mounts. Uses an existing
crane binary; image acquisition is not an experiment or model call.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[2]
SERVER = 'zhoujunye@10.123.4.30'
REMOTE = '/home/zhoujunye/MAS-information/.cache/cooperbench-images'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--authorized-full-inventory-transfer', action='store_true', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--reuse-dir', type=Path)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    crane = str(ROOT / '.cache/native-tools/crane')
    tasks = json.loads((ROOT / 'benchmarks/cooperbench/upstream/dataset/subsets/all.json').read_text())['tasks']
    def transfer(item):
        index, task = item
        name = task['repo'].removesuffix('_task').replace('_', '-')
        image = f"akhatua/cooperbench-{name}:task{int(task['task_id'])}"
        row = dict(image=image)
        logpath = args.output / f'{index}.log'
        try:
            manifest = json.loads(subprocess.check_output([crane, 'manifest', '--platform=linux/amd64', image], timeout=120))
            expected = manifest['config']['digest']
            row['image_id'] = expected
            present = subprocess.run(['ssh', '-o', 'BatchMode=yes', SERVER,
                                      'docker image inspect --format "{{.Id}}" ' + image], capture_output=True, text=True)
            if present.returncode == 0 and present.stdout.strip() == expected:
                row['status'] = 'already_verified'
            else:
                archive = args.output / f'{name}-{task["task_id"]}.tar'
                reused = False
                if args.reuse_dir:
                    candidate = args.reuse_dir / archive.name
                    try:
                        with tarfile.open(candidate) as tar:
                            info = json.load(tar.extractfile('manifest.json'))[0]
                            actual = 'sha256:' + hashlib.sha256(tar.extractfile(info['Config']).read()).hexdigest()
                            if actual == expected:
                                archive, reused = candidate, True
                    except (OSError, tarfile.TarError, KeyError, ValueError):
                        pass
                with logpath.open('x') as log:
                    if not reused:
                        subprocess.run([crane, 'pull', '--platform=linux/amd64', '--cache_path',
                                        str(ROOT / '.cache/cooperbench-images/layers'), image, str(archive)],
                                       stdout=log, stderr=subprocess.STDOUT, timeout=3600, check=True)
                    digest = hashlib.sha256()
                    with archive.open('rb') as stream:
                        for block in iter(lambda: stream.read(1024 * 1024), b''):
                            digest.update(block)
                    row['archive_sha256'] = digest.hexdigest()
                    subprocess.run(['rsync', '-az', '-e', 'ssh -o BatchMode=yes', str(archive), f'{SERVER}:{REMOTE}/'],
                                   stdout=log, stderr=subprocess.STDOUT, timeout=1800, check=True)
                    subprocess.run(['ssh', '-o', 'BatchMode=yes', SERVER, 'docker load -i ' + REMOTE + '/' + archive.name],
                                   stdout=log, stderr=subprocess.STDOUT, timeout=600, check=True)
                actual = subprocess.check_output(['ssh', '-o', 'BatchMode=yes', SERVER,
                         'docker image inspect --format "{{.Id}}" ' + image], text=True).strip()
                if actual != expected:
                    raise ValueError('Transferred image differs from official manifest')
                row['status'] = 'transferred_verified'
        except Exception as error:
            row.update(status='error', error=str(error))
        (args.output / f'{index}.json').write_text(json.dumps(row, indent=2))
        print(json.dumps(row), flush=True)
        return row
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(transfer, enumerate(tasks)))
    (args.output / 'summary.json').write_text(json.dumps(rows, indent=2))
    if any(r['status'] == 'error' for r in rows):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
