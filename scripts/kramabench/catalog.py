"""Validate an existing pinned source checkout and export public questions only."""
import argparse
from collections import Counter
from dataclasses import asdict
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from benchmarks.kramabench.tasks import load_tasks
from common.io import write_json

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    tasks, provenance = load_tasks(args.upstream)
    args.output.mkdir(parents=True, exist_ok=False)
    write_json(args.output / "tasks.json", [asdict(task) for task in tasks])
    write_json(args.output / "provenance.json", provenance)
    print(dict(Counter(task.domain for task in tasks)), "total", len(tasks))
