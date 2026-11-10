"""List only local, publicly scoreable tasks, plus exclusions and input readiness."""

import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from benchmarks.fdabench.tasks import read_catalog, mounts, REVISION
from benchmarks._external import verify_sources
from common.file_digest import DigestCache
from common.io import write_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--data", type=Path)
    parser.add_argument("--output", type=Path, help="Fresh public ID/hash/readiness receipt; no questions or references")
    args = parser.parse_args(argv)
    if args.output and args.output.exists():
        raise FileExistsError(args.output)
    revision = subprocess.check_output(["git", "-C", str(args.upstream), "rev-parse", "HEAD"], text=True).strip()
    if revision != REVISION:
        raise ValueError("FDABench upstream revision differs")
    verify_sources(args.upstream, "fdabench")
    tasks, excluded = read_catalog(args.tasks)
    readiness = []
    checked = {}
    cache = DigestCache(args.data.parent / "asset-digests.sqlite") if args.data else None
    for task in tasks:
        if args.data:
            key = (task.reference["database_type"], task.db, "vector_search" in task.reference["tools_available"])
            if key not in checked:
                try:
                    mounts(task, args.data, hash_file=cache.digest)
                    checked[key] = dict(status="inputs_ready")
                except ValueError as error:
                    checked[key] = dict(status="missing_inputs", reason=str(error))
            readiness.append(dict(task_id=task.id, **checked[key]))
    result = dict(benchmark="fdabench", revision=revision, tasks=len(tasks),
                         task_ids=[t.id for t in tasks], categories=dict(Counter(t.category for t in tasks)),
                         task_sources={t.id: t.source_sha256 for t in tasks},
                         excluded=dict(Counter(r["reason"] for r in excluded)),
                         excluded_tasks=excluded, readiness=readiness,
                         readiness_counts=dict(Counter(r["status"] for r in readiness)), paid_calls=0)
    if args.output:
        write_json(args.output, result)
        print(json.dumps({k: result[k] for k in ("tasks", "categories", "excluded", "readiness_counts", "paid_calls")}))
    else:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
