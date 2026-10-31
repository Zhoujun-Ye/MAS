#!/usr/bin/env python3
"""Cache public dependencies before offline gates, without tests or model access."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from benchmarks.cooperbench.adapter import verify_checkout
from benchmarks.cooperbench.selection import all_task_pairs
from benchmarks.cooperbench.environment import CACHE, VERSION, INDEX, inspect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--recipe-revision', type=int, default=1,
                        help='New immutable receipt/image revision; never overwrite an earlier preparation')
    parser.add_argument('--authorized-public-dependency-preparation', action='store_true', required=True)
    args = parser.parse_args()
    if args.recipe_revision < 1:
        raise ValueError('Recipe revision must be positive')
    allowed = {p.image: p.repo for p in all_task_pairs(verify_checkout())
               if p.repo in ('dottxt_ai_outlines_task', 'dspy_task', 'huggingface_datasets_task',
                             'llama_index_task', 'openai_tiktoken_task')}
    if args.image not in allowed:
        raise ValueError('No audited dependency preparation recipe for this official image')
    source = inspect(args.image)['Id']
    suffix = '' if args.recipe_revision == 1 else '-r' + str(args.recipe_revision)
    receipt_path = CACHE / (source.split(':')[1] + suffix + '.json')
    if receipt_path.exists():
        raise ValueError('An immutable preparation receipt already exists')
    args.output.mkdir(parents=True, exist_ok=False)
    name = 'mas-info-prepare-' + uuid.uuid4().hex[:12]
    tag = 'mas-information/cooperbench-prepared:' + source.split(':')[1][:16] + suffix
    recipes = {
        'dottxt_ai_outlines_task': [
            ['uv', 'sync', '--index-url', INDEX, '--no-install-project'],
            ['uv', 'pip', 'install', '--system', '--index-url', INDEX, '-e', '.'],
            ['uv', 'pip', 'install', '--system', '--index-url', INDEX, 'pytest', 'pytest-xdist', 'pytest-mock', 'setuptools-scm'],
        ],
        'dspy_task': [
            ['python3', '-m', 'pip', 'install', '--index-url', INDEX, '-e', '.[dev]', 'litellm[proxy]==1.77.1'],
        ],
        'huggingface_datasets_task': [
            ['python3', '-m', 'pip', 'download', '--index-url', INDEX, '--dest', '/opt/cooperbench-wheels',
             '--only-binary=:all:', '--no-deps', 'pyarrow==20.0.0'],
        ],
        'llama_index_task': [
            ['python3', '-c', '''import importlib.util, pathlib, shutil
source = pathlib.Path(importlib.util.find_spec('llama_index.core').origin).parent / '_static'
target = pathlib.Path('/opt/cooperbench-data')
target.mkdir(exist_ok=True)
for name in ('nltk_cache', 'tiktoken_cache'):
    shutil.copytree(source / name, target / name, dirs_exist_ok=True)
'''],
            ['uv', 'pip', 'uninstall', '--system', 'llama-index-core'],
            ['uv', 'cache', 'clean', 'llama-index-core'],
            ['python3', '-m', 'pip', 'cache', 'purge'],
            ['uv', 'pip', 'install', '--system', '--index-url', INDEX, '-e', '.', '-e', './llama-index-core'],
            ['python3', '-c', '''import importlib.util, pathlib
origin = pathlib.Path(importlib.util.find_spec('llama_index.core').origin).resolve()
assert origin.is_relative_to(pathlib.Path('/workspace/repo/llama-index-core')), origin
'''],
        ],
        'openai_tiktoken_task': [
            ['python3', '-m', 'pip', 'install', '--index-url', INDEX,
             'setuptools>=62.4', 'wheel', 'setuptools-rust>=1.5.2'],
        ],
    }
    commands = recipes[allowed[args.image]]
    commands += [
        ['git', 'reset', '--hard', 'HEAD'],
        ['git', 'clean', '-fd' if allowed[args.image] == 'openai_tiktoken_task' else '-fdx'],
    ]
    subprocess.run(['docker', 'run', '-d', '--name', name, '--label', 'project=MAS-information',
                    '--network', 'bridge', '--cpus', '4', '--memory', '16g', '--pids-limit', '512',
                    '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--entrypoint', '',
                    '-w', '/workspace/repo', source, 'sleep', 'infinity'], check=True, capture_output=True)
    try:
        with (args.output / 'prepare.log').open('x') as log:
            for command in commands:
                log.write(json.dumps(command) + '\n')
                log.flush()
                subprocess.run(['docker', 'exec', name, *command], stdout=log, stderr=subprocess.STDOUT,
                               timeout=3600, check=True)
        subprocess.run(['docker', 'commit', '--change', 'LABEL mas-information.source-image=' + source,
                        name, tag], check=True, capture_output=True, timeout=900)
        receipt = dict(version=VERSION, source_image_id=source, image_id=inspect(tag)['Id'],
                       recipe_revision=args.recipe_revision,
                       official_image=args.image, commands=commands, package_index=INDEX,
                       preparation_only_network=True, paid_calls=0)
        CACHE.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, indent=2))
        (args.output / 'receipt.json').write_text(json.dumps(receipt, indent=2))
        print(json.dumps(receipt), flush=True)
    finally:
        subprocess.run(['docker', 'rm', '-f', name], check=True, capture_output=True, timeout=30)


if __name__ == '__main__':
    main()
