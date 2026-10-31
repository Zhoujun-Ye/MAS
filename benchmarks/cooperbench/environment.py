"""Resolve audited dependency-only derivatives of official task images."""
import json
import hashlib
from pathlib import Path
import subprocess
from .offline_assets import TOKENIZER_ASSETS

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / '.cache/cooperbench-environments'
VERSION = 'offline-dependencies-v1'
INDEX = 'https://pypi.tuna.tsinghua.edu.cn/simple'


def inspect(image):
    return json.loads(subprocess.check_output(['docker', 'image', 'inspect', image], text=True))[0]


def resolve(image):
    source = inspect(image)
    runtime_env = {}
    if image.startswith('akhatua/cooperbench-dottxt-ai-outlines:'):
        runtime_env['UV_INDEX_URL'] = INDEX
    if image.startswith('akhatua/cooperbench-huggingface-datasets:'):
        runtime_env.update(PIP_FIND_LINKS='/opt/cooperbench-wheels', UV_FIND_LINKS='/opt/cooperbench-wheels')
    if image.startswith('akhatua/cooperbench-llama-index:'):
        runtime_env.update(NLTK_DATA='/opt/cooperbench-data/nltk_cache',
                           TIKTOKEN_CACHE_DIR='/opt/cooperbench-data/tiktoken_cache')
        receipt = json.loads((ROOT / '.cache/cooperbench-public/receipt.json').read_text())
        if hashlib.sha256((ROOT / '.cache/cooperbench-public/dummy.pdf').read_bytes()).hexdigest() != receipt['sha256']:
            raise ValueError('Public asset receipt mismatch')
        runtime_env.update(COOPERBENCH_PUBLIC_ASSETS='pdf', COOPERBENCH_PDF_SHA256=receipt['sha256'])
    if image == 'akhatua/cooperbench-dottxt-ai-outlines:task1706':
        runtime_env['COOPERBENCH_PUBLIC_ASSETS'] = 'gguf'
    if image == 'akhatua/cooperbench-openai-tiktoken:task0':
        for url, digest in TOKENIZER_ASSETS.items():
            path = ROOT / '.cache/cooperbench-public/tiktoken' / hashlib.sha1(url.encode()).hexdigest()
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError('Public tokenizer data differs from source hash')
        runtime_env.update(COOPERBENCH_PUBLIC_ASSETS='tiktoken',
                           TIKTOKEN_CACHE_DIR='/opt/cooperbench-public/tiktoken')
    path = CACHE / (source['Id'].split(':')[1] + '.json')
    revisions = list(CACHE.glob(source['Id'].split(':')[1] + '-r*.json'))
    if revisions:
        path = max(revisions, key=lambda p: int(p.stem.rsplit('-r', 1)[1]))
    if not path.exists():
        return dict(source_image_id=source['Id'], image_id=source['Id'], provisioning=None, runtime_env=runtime_env)
    receipt = json.loads(path.read_text())
    if receipt['source_image_id'] != source['Id'] or receipt['version'] != VERSION:
        raise ValueError('Dependency image receipt mismatch')
    prepared = inspect(receipt['image_id'])
    labels = prepared['Config'].get('Labels') or {}
    if labels.get('mas-information.source-image') != source['Id']:
        raise ValueError('Dependency image is not bound to its official source')
    return dict(source_image_id=source['Id'], image_id=prepared['Id'], provisioning=receipt, runtime_env=runtime_env)
