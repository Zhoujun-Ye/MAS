#!/usr/bin/env python3
"""Freeze twenty public feature pairs before gates or model outcomes."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from benchmarks.cooperbench.adapter import verify_checkout
from benchmarks.cooperbench.selection import choose, lite, expansion, started_inventory

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--lite', action='store_true')
    mode.add_argument('--new-100', action='store_true')
    parser.add_argument('--prior-outputs', type=Path, default=Path('outputs/cooperbench'))
    args = parser.parse_args()
    dataset = verify_checkout()
    data = (expansion(dataset, *started_inventory(args.prior_outputs)) if args.new_100
            else (lite if args.lite else choose)(dataset))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(data, stream, indent=2)
    print(json.dumps(data))
