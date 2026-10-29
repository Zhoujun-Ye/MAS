"""Official BrowseComp-Plus queries, answers and relevance judgments."""

from __future__ import annotations

import json
from pathlib import Path


def load_tasks(path: Path) -> list[dict]:
    """Rows with query_id, query and answer."""
    with Path(path).open(encoding="utf-8") as file:
        rows = [json.loads(line) for line in file if line.strip()]
    for row in rows:
        row["query_id"] = str(row["query_id"])
    return rows


def load_qrels(path: Path) -> dict[str, list[str]]:
    """TREC qrels ``qid Q0 docid rel`` -> relevant docids per query."""
    qrels: dict[str, list[str]] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        qid, _, docid, rel = line.split()
        if int(rel) > 0:
            qrels.setdefault(qid, []).append(docid)
    return qrels
