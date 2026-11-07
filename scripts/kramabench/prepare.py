"""Prepare the complete pinned input lake and an explicitly authorized image.

No model, judge, solution import or implicit dataset download. Input checkout must
already be populated. Every Git blob and SHA-256 is verified before image testing.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from benchmarks.kramabench.tasks import DOMAINS, UPSTREAM_COMMIT, load_tasks
from common.io import write_json

REQUIREMENTS = """numpy==2.2.6
pandas==2.2.3
scipy==1.15.3
openpyxl==3.1.5
pypdf==5.6.0
pyarrow==20.0.0
geopandas==1.0.1
pyogrio==0.11.0
shapely==2.1.1
pyproj==3.7.1
cdflib==1.3.4
astropy==7.0.2
sgp4==2.24
beautifulsoup4==4.13.4
lxml==5.4.0
html5lib==1.1
statsmodels==0.14.4
scikit-learn==1.6.1
matplotlib==3.10.3
"""

FORMAT_SMOKE = r'''
import json
from collections import Counter
from pathlib import Path
import numpy as np
import pandas as pd
import scipy, openpyxl, pypdf, pyarrow, geopandas, pyogrio, shapely, pyproj
import cdflib, astropy, sgp4, bs4, lxml, html5lib, statsmodels, sklearn, matplotlib
root = Path('/data')
counts = Counter()
opened = []
for path in sorted(root.glob('*/input/**/*')):
    if not path.is_file():
        continue
    suffix = path.suffix.lower()
    counts[suffix] += 1
    if suffix == '.xlsx':
        with pd.ExcelFile(path, engine='openpyxl') as book:
            assert book.sheet_names
            pd.read_excel(book, sheet_name=book.sheet_names[0], nrows=2)
        opened.append(str(path.relative_to(root)))
    elif suffix == '.gpkg':
        layers = geopandas.list_layers(path)
        assert len(layers)
        geopandas.read_file(path, layer=layers.iloc[0]['name'], rows=1)
        opened.append(str(path.relative_to(root)))
    elif suffix == '.cdf':
        cdf = cdflib.CDF(path)
        assert cdf.cdf_info()
        opened.append(str(path.relative_to(root)))
    elif suffix == '.npz':
        with np.load(path, allow_pickle=False) as archive:
            assert archive.files
        opened.append(str(path.relative_to(root)))
    else:
        # Input scripts are read as data, never imported or executed.
        with path.open('rb') as stream:
            stream.read(4096)
print(json.dumps({'file_counts': dict(counts), 'binary_files_opened': opened,
                  'network': 'none', 'scope': 'imports, readability and binary-format smoke; not task solutions'}))
'''


def verify_inputs(upstream,*,cache=None):
    tasks, provenance = load_tasks(upstream)
    raw = subprocess.check_output(['git', '-C', str(upstream), 'ls-tree', '-r', '-z', 'HEAD', 'data'])
    entries, files, domains = {}, {}, Counter()
    for entry in raw.split(b'\0'):
        if not entry:
            continue
        meta, encoded_path = entry.split(b'\t', 1)
        mode, kind, oid = meta.decode().split()
        relative = encoded_path.decode()
        parts = Path(relative).parts
        if len(parts) < 4 or parts[1] not in DOMAINS or parts[2] != 'input':
            raise ValueError('Unexpected non-input asset: ' + relative)
        if mode not in ('100644', '100755') or kind != 'blob':
            raise ValueError('Non-regular input: ' + relative)
        entries[relative] = oid
    actual = {str(p.relative_to(upstream)) for p in (upstream / 'data').rglob('*') if p.is_file() or p.is_symlink()}
    if actual != set(entries):
        raise ValueError(f'Input inventory mismatch: missing={set(entries)-actual}, extra={actual-set(entries)}')
    for relative, oid in sorted(entries.items()):
        path = upstream / relative
        if path.is_symlink():
            raise ValueError('Input symlink: ' + relative)
        size = path.stat().st_size
        if cache is not None:
            files[relative]={'bytes':size,'git_blob':oid,'sha256':cache.digest(path,git_blob=oid)}
            domains[Path(relative).parts[1]]+=1
            continue
        git_hash = hashlib.sha1(f'blob {size}\0'.encode())
        sha256 = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                git_hash.update(block)
                sha256.update(block)
        if git_hash.hexdigest() != oid:
            raise ValueError('Input content differs from pinned Git blob: ' + relative)
        files[relative] = {'bytes': size, 'git_blob': oid, 'sha256': sha256.hexdigest()}
        domains[Path(relative).parts[1]] += 1
    return dict(provenance=provenance, tasks=len(tasks), files=files, domain_counts=dict(domains),
                total_files=len(files), total_bytes=sum(f['bytes'] for f in files.values()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--base-image', required=True, help='Already pulled, digest-pinned base image')
    parser.add_argument('--image', required=True, help='New dedicated image tag; existing tags refused')
    parser.add_argument('--execute', action='store_true', help='Build only after explicit provisioning authorization')
    args = parser.parse_args()
    inventory = verify_inputs(args.upstream.resolve())
    if not args.execute:
        print(json.dumps(dict(status='planned', input_files=inventory['total_files'],
                              input_bytes=inventory['total_bytes'], image=args.image,
                              paid_calls=0, environment_changed=False), indent=2))
        return
    args.output.mkdir(parents=True, exist_ok=False)
    try:
        write_json(args.output / 'inputs.json', inventory)
        existing = subprocess.run(['docker', 'image', 'inspect', args.image], capture_output=True)
        if existing.returncode == 0:
            raise ValueError('Refusing to overwrite an existing image tag')
        base = json.loads(subprocess.check_output(['docker', 'image', 'inspect', args.base_image]))[0]
        context = args.output / 'build'
        context.mkdir()
        (context / 'requirements.txt').write_text(REQUIREMENTS)
        dockerfile = f'''FROM {args.base_image}
RUN sed -i 's|http://deb.debian.org|https://mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources && apt-get update && apt-get install -y --no-install-recommends git coreutils ca-certificates && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --index-url https://pypi.tuna.tsinghua.edu.cn/simple -r /tmp/requirements.txt && pip check && rm /tmp/requirements.txt
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MPLCONFIGDIR=/tmp/matplotlib HOME=/tmp LANG=C.UTF-8
WORKDIR /workspace
'''
        (context / 'Dockerfile').write_text(dockerfile)
        with (args.output / 'build.log').open('x') as log:
            subprocess.run(['docker', 'build', '--network', 'default', '--tag', args.image, str(context)],
                           stdout=log, stderr=subprocess.STDOUT, check=True)
        image = json.loads(subprocess.check_output(['docker', 'image', 'inspect', args.image]))[0]
        packages = subprocess.check_output(['docker', 'run', '--rm', '--network', 'none', args.image,
                                           'pip', 'freeze'], text=True)
        (args.output / 'packages.txt').write_text(packages)
        smoke = subprocess.check_output(['docker', 'run', '--rm', '--network', 'none', '--cpus', '2',
            '--memory', '4g', '--pids-limit', '128', '--mount',
            f'type=bind,src={args.upstream.resolve() / "data"},dst=/data,readonly',
            args.image, 'python3', '-I', '-c', FORMAT_SMOKE], text=True)
        write_json(args.output / 'format-smoke.json', json.loads(smoke))
        write_json(args.output / 'environment.json', {'status': 'prepared', 'upstream_commit': UPSTREAM_COMMIT,
            'image_tag': args.image, 'image_id': image['Id'], 'base_image_id': base['Id'],
            'base_repo_digests': base.get('RepoDigests'), 'dockerfile_sha256': hashlib.sha256(dockerfile.encode()).hexdigest(),
            'packages_sha256': hashlib.sha256(packages.encode()).hexdigest(),
            'tasks': inventory['tasks'], 'input_files': inventory['total_files'], 'input_bytes': inventory['total_bytes'],
            'paid_calls': 0, 'solution_execution': False})
        print(json.dumps({'status': 'prepared', 'input_files': inventory['total_files'],
                          'input_bytes': inventory['total_bytes'], 'domains': inventory['domain_counts'],
                          'image_id': image['Id'], 'output': str(args.output)}, indent=2))
    except Exception as error:
        write_json(args.output / 'failure.json', {'type': type(error).__name__, 'error': str(error)})
        raise


if __name__ == '__main__':
    main()
