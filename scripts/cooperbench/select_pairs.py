#!/usr/bin/env python3
"""Freeze twenty public feature pairs before gates or model outcomes."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from benchmarks.cooperbench.adapter import verify_checkout
from benchmarks.cooperbench.selection import choose, lite

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--lite', action='store_true')
    args = parser.parse_args()
    data = (lite if args.lite else choose)(verify_checkout())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(data, stream, indent=2)
    print(json.dumps(data))
