"""Allowlisted FDABench inputs, excluding hidden-answer and cloud tasks."""

import hashlib
import json
import math
from pathlib import Path

from benchmarks._external import Task, safe_id, unique, digest

UPSTREAM = "https://github.com/fdabench/FDAbench"
REVISION = "72e50a2b59798848a06ad30c5d8a39248c1228bf"
DATASET = "FDAbench2026/FDAbench-Full"
DATA_REVISION = "0e05e5ec2c95fbe462bed0cba1882f99989ab34e"
RELEASE_SHA256 = {
    "report.jsonl": "35022d66c909c13d35ea2b473f249e6e8e3bef0c968e7c234e96cf971bac11df",
    "single.jsonl": "2b45449da0cad5587c91793be44da70b74f48ce0011a773c256ae7adef2ccfe7",
    "multiple.jsonl": "53bc4d871f2a7b955c9f09fd30edbc5f09885d3eeacc69e4760c3e7165a9fcc5",
}
DIMENSIONS = {"SQL_ACCURACY", "EXTERNAL_INTEGRATION", "LOGICAL_REASONING", "COMPLETENESS"}


def local_database(row):
    kind = row.get("database_type", "").lower()
    return kind in {"bird", "spider1", "dabstep", "local"} or (
        kind == "spider2-lite" and str(row.get("instance_id", "")).startswith("local"))


def exclusion(row):
    kind = row.get("question_type")
    if kind in {"single_choice", "multiple_choice"}:
        answer, options = row.get("correct_answer"), row.get("options")
        if not isinstance(answer, list) or not answer:
            return "no_public_answer"
        if (not isinstance(options, dict) or any(not isinstance(x, str) for x in answer)
                or len(set(answer)) != len(answer) or set(answer) - set(options)
                or (kind == "single_choice" and len(answer) != 1)):
            return "invalid_public_answer"
    elif kind == "report":
        rubric = row.get("rubric")
        dimensions = rubric.get("evaluation_dimensions") if isinstance(rubric, dict) else None
        if not isinstance(dimensions, dict) or set(dimensions) != DIMENSIONS:
            return "missing_report_rubric"
        if not all(isinstance(row.get(key), str) and row[key].strip()
                   for key in ("ground_truth_report", "sql_result")):
            return "missing_report_reference"
        for value in dimensions.values():
            if (not isinstance(value, dict) or not isinstance(value.get("criteria"), str)
                    or not value["criteria"].strip() or type(value.get("weight")) not in (int, float)
                    or not math.isfinite(value["weight"]) or value["weight"] <= 0):
                return "invalid_report_rubric"
        if not all(isinstance(row.get(k), dict) for k in ("frozen_web_search", "frozen_vector_search")):
            return "missing_report_reference"
        chain = rubric.get("chain_validation")
        if not isinstance(chain, list) or not chain or any(
                not isinstance(c, dict) or not {"step", "tool", "rationale"} <= c.keys() for c in chain):
            return "missing_report_reference"
    else:
        return "unsupported_question_type"
    if not local_database(row):
        return "cloud_database_disabled"
    return None


def read_catalog(path):
    path = Path(path)
    files = [path / (part + ".jsonl") for part in ("report", "single", "multiple")] if path.is_dir() else [path]
    if path.is_dir():
        if {p.name for p in path.glob("*.jsonl")} != set(RELEASE_SHA256):
            raise ValueError("FDABench pinned release inventory differs")
        for source in files:
            if source.is_symlink() or digest(source) != RELEASE_SHA256[source.name]:
                raise ValueError("FDABench pinned release content differs")
    tasks, excluded, seen = [], [], set()
    for source in files:
        for line in source.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            identity = safe_id(row["task_id"])
            if identity in seen:
                raise ValueError("Duplicate FDABench task_id: " + identity)
            seen.add(identity)
            reason = exclusion(row)
            if reason:
                excluded.append(dict(task_id=identity, reason=reason))
                continue
            query, options = row.get("query"), row.get("options")
            if not isinstance(query, str) or not query.strip():
                raise ValueError("Missing FDABench query: " + identity)
            db = safe_id(row["db"])
            question = query.strip()
            if row["question_type"] != "report":
                if any(not isinstance(k, str) or len(k) != 1 or not "A" <= k <= "Z"
                       or not isinstance(v, str) or not v.strip() for k, v in options.items()):
                    raise ValueError("Invalid FDABench options: " + identity)
                question += "\n\nOptions:\n" + "\n".join(f"{k}. {v}" for k, v in options.items())
                question += '\nReturn only a JSON array of selected option letters as final_answer text, e.g. ["A"].'
            else:
                question += "\n\nReturn the analytical report as final_answer text."
            tools = row.get("tools_available")
            if not isinstance(tools, list) or any(not isinstance(t, str) for t in tools):
                raise ValueError("Missing FDABench tool access declaration: " + identity)
            sha = hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
            tasks.append(Task(identity, "fdabench", question, row["question_type"], "web_search" in tools,
                              sha, db=db, reference=row))
    return tasks, excluded


def load_tasks(path):
    return unique(read_catalog(path)[0])


def needs_corpus(task):
    return "vector_search" in task.reference["tools_available"]


def database_path(task, data):
    """Explicit namespace prevents equal names in different releases colliding."""
    family = task.reference["database_type"].lower()
    return Path(data) / family / task.db / (task.db + ".sqlite")


def mounts(task, data, *, hash_file=digest):
    from benchmarks._external import asset_manifest
    database = database_path(task, data)
    root = Path(data).resolve(strict=True)
    if any(p.is_symlink() for p in (database, database.parent, database.parent.parent)):
        raise ValueError("FDABench database symlinks are forbidden")
    if not database.is_file() or not database.resolve().is_relative_to(root):
        raise ValueError("Missing local FDABench database: " + str(database))
    with database.open("rb") as stream:
        if stream.read(16) != b"SQLite format 3\x00":
            raise ValueError("FDABench input is not hydrated SQLite")
    result = [(database, "/data/database.sqlite", True)]
    if needs_corpus(task):
        corpus = Path(data) / "corpus"
        if corpus.is_symlink():
            raise ValueError("FDABench corpus must not be a symlink")
        # Corpus is a separately prepared raw-data directory, never frozen search answers.
        receipt = Path(data) / "corpus-receipt.json"
        if not receipt.is_file():
            raise ValueError("Missing FDABench raw corpus receipt")
        expected = json.loads(receipt.read_text())
        if expected.get("kind") != "fdabench-raw-corpus-v1" or expected.get("files") != asset_manifest(corpus, hash_file=hash_file):
            raise ValueError("FDABench raw corpus differs from its preparation receipt")
        result.append((corpus, "/corpus", True))
        index = Path(data) / "corpus-search.sqlite"
        index_receipt = Path(data) / "corpus-index-receipt.json"
        from common.io import fingerprint
        if not index.is_file() or index.is_symlink() or not index_receipt.is_file():
            raise ValueError("Missing FDABench document index")
        index_metadata = json.loads(index_receipt.read_text())
        if (index_metadata.get("index_sha256") != hash_file(index)
                or index_metadata.get("corpus_sha256") != fingerprint(expected["files"])):
            raise ValueError("FDABench document index differs from corpus receipt")
        result.append((index, "/corpus-search.sqlite", True))
    return result
