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
    parser.add_argument("--mode", choices=["single", "team", "both"], default="team")
    parser.add_argument("--leader-mode", choices=["full", "coordinator"],
                        help="Team defaults to coordinator with no domain tools; full is an explicit ablation")
    args = parser.parse_args()
    if args.mode == "single" and args.leader_mode not in (None, "full"):
        parser.error("--leader-mode applies only to Team")
    result = comparison_smoke(args.output, leader_mode=args.leader_mode or "coordinator") if args.mode == "both" else smoke(
        args.output, mode=args.mode, leader_mode=args.leader_mode)
    print(json.dumps(result, indent=2))
