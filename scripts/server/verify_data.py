"""Private real-data integrity and official SQL reference self-check, no model calls."""

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from benchmarks._external import asset_manifest, digest, verify_sources, write_jsonl, jsonl
from common.io import write_json
from benchmarks.dataclawbench.tasks import load_tasks as dc_tasks
from benchmarks.hybriddeepresearch.tasks import load_tasks as hdr_tasks
from benchmarks.hybriddeepresearch.evaluation import evaluation_rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute-sql", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    args.output.mkdir(parents=True, exist_ok=False)
    dc_root, hdr_root = (args.root / name / "upstream" for name in ("dataclawbench", "hybriddeepresearch"))
    verify_sources(dc_root, "dataclawbench")
    verify_sources(hdr_root, "hybriddeepresearch")
    dc = dc_tasks(dc_root)
    hdr = hdr_tasks(args.root / "hybriddeepresearch/release/hybrid_ds_release/hybrid_ds_release.jsonl")
    database_root = args.root / "hybriddeepresearch/data"
    databases = {}
    for name in sorted({task.db for task in hdr}):
        path = database_root / name / (name + "_template.sqlite")
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as conn:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            tables = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
        if integrity != "ok" or not tables:
            raise ValueError("Database integrity/readability failure: " + name)
        databases[name] = dict(sha256=digest(path), tables=tables, integrity=integrity)
    result = dict(dataclaw_tasks=len(dc), hdr_tasks=len(hdr),
        hdr_categories=dict(Counter(t.category for t in hdr)), databases=databases,
        dataclaw_assets=asset_manifest(dc_root / "assets/database"),
        dataclaw_clear_assets=asset_manifest(dc_root / "assets/database_clear"),
        hdr_assets=asset_manifest(database_root), paid_calls=0, sql_self_check=None)
    if args.execute_sql:
        sql_tasks = [task for task in hdr if task.category == "search_to_sql"]
        rows = evaluation_rows(sql_tasks, {task.id: dict(final_answer="```sql\n" + task.reference["sql"] + "\n```")
                                         for task in sql_tasks})["s2sql"]
        source = args.output / "private-reference-self-inputs.jsonl"
        target = args.output / "private-reference-self-results.jsonl"
        write_jsonl(source, rows)
        with (args.output / "sql-stdout.log").open("x") as stdout, (args.output / "sql-stderr.log").open("x") as stderr:
            subprocess.run([sys.executable, str(hdr_root / "evaluation/s2sql_eval.py"),
                "--input", str(source), "--output", str(target), "--db-root", str(database_root)],
                check=True, stdout=stdout, stderr=stderr, timeout=1800)
        graded = jsonl(target)
        result["sql_self_check"] = dict(total=len(graded), matched=sum(row["match"] for row in graded),
            failures=[dict(instance_id=row["instance_id"], reason_class=row["reason"].split(":",1)[0])
                      for row in graded if not row["match"]], model_quality_evidence=False)
    write_json(args.output / "verification.json", result)
    print(json.dumps({k: result[k] for k in ("dataclaw_tasks", "hdr_tasks", "hdr_categories", "paid_calls", "sql_self_check")}))


if __name__ == "__main__":
    main()
