#!/usr/bin/env python3
"""Fetch a public fixture on the server, without tests, patches or model calls."""
import hashlib
import argparse
import json
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from benchmarks.cooperbench.offline_assets import PDF_URL, TOKENIZER_ASSETS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset', choices=('pdf', 'tiktoken'), default='pdf')
    args = parser.parse_args()
    root = ROOT / '.cache/cooperbench-public'
    if args.asset == 'tiktoken':
        root = root / 'tiktoken'
        root.mkdir(parents=True, exist_ok=False)
        rows = []
        for url, expected in TOKENIZER_ASSETS.items():
            with urllib.request.urlopen(url, timeout=60) as response:
                body = response.read()
            digest = hashlib.sha256(body).hexdigest()
            if digest != expected:
                raise ValueError('Tokenizer data differs from task source hash: ' + url)
            filename = hashlib.sha1(url.encode()).hexdigest()
            (root / filename).write_bytes(body)
            rows.append(dict(url=url, sha256=digest, bytes=len(body), filename=filename))
        receipt = dict(assets=rows, paid_calls=0)
        (root / 'receipt.json').write_text(json.dumps(receipt, indent=2))
        print(json.dumps(receipt))
        return
    root.mkdir(parents=True, exist_ok=False)
    with urllib.request.urlopen(PDF_URL, timeout=60) as response:
        body = response.read()
        if response.status != 200 or not body.startswith(b'%PDF-'):
            raise ValueError('Expected the real public PDF')
    receipt = dict(url=PDF_URL, sha256=hashlib.sha256(body).hexdigest(), bytes=len(body), paid_calls=0)
    (root / 'dummy.pdf').write_bytes(body)
    (root / 'receipt.json').write_text(json.dumps(receipt, indent=2))
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
