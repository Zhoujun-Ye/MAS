#!/usr/bin/env python3
"""Fetch a pinned source/dataset checkout; no installs, containers or model calls."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from benchmarks.cooperbench.adapter import UPSTREAM, URL, REVISION, verify_checkout, discover


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fetch', action='store_true')
    args = parser.parse_args()
    if not UPSTREAM.exists():
        if not args.fetch:
            parser.error('Missing upstream checkout; pass --fetch to download the pinned source')
        UPSTREAM.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['git', 'clone', '--no-checkout', URL, str(UPSTREAM)], check=True)
        subprocess.run(['git', '-C', str(UPSTREAM), 'checkout', '--detach', REVISION], check=True)
    dataset = verify_checkout()
    pairs = discover(dataset)
    print(json.dumps(dict(revision=REVISION, pairs=len(pairs),
        tasks=len({(p.repo, p.task_id) for p in pairs}), repos=len({p.repo for p in pairs}),
        paid_calls=0, containers_started=0)))


if __name__ == '__main__':
    main()
