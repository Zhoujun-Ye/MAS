"""Prepare BrowseComp-Plus inputs on the server: verified queries and the snippet tokenizer.

  .venv/bin/python scripts/prepare_bcp.py

Copies the 830 official test queries that the agent-team project decrypted
from the pinned dataset revision, checks their ids against the official
evidence qrels, and downloads the Qwen3-0.6B tokenizer used for official
snippet truncation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mas_info.config import ROOT
from mas_info.runner import write_json

SOURCE = Path("/home/zhoujunye/agent-team/.cache/browsecomp-plus-test-20261019-02")
QRELS = ROOT / "external/BrowseComp-Plus/topics-qrels/qrel_evidence.txt"
TOKENIZER_REPO = "Qwen/Qwen3-0.6B"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch(url: str, timeout: int = 300) -> bytes:
    # hf-mirror.com answers 403 to urllib's default User-Agent.
    request = urllib.request.Request(url, headers={"User-Agent": "curl/8.5.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def prepare_tasks(source: Path) -> None:
    target = ROOT / "data/bcp/tasks.jsonl"
    rows = [json.loads(line) for line in (source / "test.jsonl").read_text().splitlines() if line.strip()]
    ids = [str(row["query_id"]) for row in rows]
    official = {line.split()[0] for line in QRELS.read_text().splitlines() if line.strip()}
    if len(rows) != 830 or len(set(ids)) != 830 or set(ids) != official:
        raise ValueError("Queries differ from the official 830-query test set")
    if any(not row.get("query") or not row.get("answer") for row in rows):
        raise ValueError("Missing query or answer text")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source / "test.jsonl", target)
    write_json(
        target.with_name("provenance.json"),
        {
            "source": str(source / "test.jsonl"),
            "sha256": sha256(target),
            "count": len(rows),
            "ids_checked_against": str(QRELS.relative_to(ROOT)),
            "upstream": json.loads((source / "provenance.json").read_text()),
        },
    )
    print(f"{target}: {len(rows)} verified queries")


def prepare_tokenizer(endpoint: str) -> None:
    folder = ROOT / ".cache/qwen3-0.6b"
    revision = json.loads(fetch(f"{endpoint}/api/models/{TOKENIZER_REPO}"))["sha"]
    target = folder / "tokenizer.json"
    folder.mkdir(parents=True, exist_ok=True)
    url = f"{endpoint}/{TOKENIZER_REPO}/resolve/{revision}/tokenizer.json"
    target.write_bytes(fetch(url))
    write_json(
        folder / "provenance.json",
        {"repo": TOKENIZER_REPO, "revision": revision, "url": url, "sha256": sha256(target)},
    )
    print(f"{target}: {TOKENIZER_REPO}@{revision}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--hf-endpoint", default=os.environ.get("HF_ENDPOINT", "https://hf-mirror.com"))
    args = parser.parse_args()
    prepare_tasks(args.source)
    prepare_tokenizer(args.hf_endpoint.rstrip("/"))


if __name__ == "__main__":
    main()
