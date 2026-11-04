"""Inspect local task coverage without exporting questions or reference answers."""

import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess

from benchmarks.dataclawbench.tasks import load_tasks as dataclaw_tasks, REVISION as DC_REVISION
from benchmarks.hybriddeepresearch.tasks import load_tasks as hybrid_tasks, REVISION as HDR_REVISION
from benchmarks._external import verify_sources


def main(argv=None, *, benchmark):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True)
    if benchmark == "hybriddeepresearch":
        parser.add_argument("--tasks", type=Path, required=True)
    args = parser.parse_args(argv)
    revision = subprocess.check_output(["git", "-C", str(args.upstream), "rev-parse", "HEAD"], text=True).strip()
    expected = DC_REVISION if benchmark == "dataclawbench" else HDR_REVISION
    if revision != expected:
        raise ValueError("Upstream checkout differs from pinned revision")
    verify_sources(args.upstream, benchmark)
    tasks = dataclaw_tasks(args.upstream) if benchmark == "dataclawbench" else hybrid_tasks(args.tasks)
    print(json.dumps(dict(benchmark=benchmark, revision=revision, tasks=len(tasks),
                         categories=dict(Counter(t.category for t in tasks)),
                         task_ids=[t.id for t in tasks], paid_calls=0), indent=2))
    return 0
