"""No paid requests: scripted KramaBench adapter verification."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from benchmarks.kramabench.offline import comparison_smoke, smoke

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=["single", "mas", "both"], default="mas")
    args = parser.parse_args()
    result = comparison_smoke(args.output) if args.mode == "both" else smoke(args.output, mode=args.mode)
    print(json.dumps(result, indent=2))
