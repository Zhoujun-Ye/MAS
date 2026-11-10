"""Build a local lexical corpus index explicitly, without embeddings or API calls."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from benchmarks._external import asset_manifest, digest
from common.file_digest import DigestCache
from common.io import write_json, fingerprint
from harness.runtime_support.documents import build


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps(dict(status="planned", paid_calls=0)))
        return 0
    data = args.data.resolve(strict=True)
    source = json.loads((data / "corpus-receipt.json").read_text())
    cache = DigestCache(data.parent / "asset-digests.sqlite")
    files = asset_manifest(data / "corpus", hash_file=cache.digest)
    if source.get("kind") != "fdabench-raw-corpus-v1" or source["files"] != files:
        raise ValueError("Raw corpus has changed")
    index = data / "corpus-search.sqlite"
    receipt = build(data / "corpus", index)
    receipt.update(corpus_sha256=fingerprint(files), index_sha256=digest(index))
    write_json(data / "corpus-index-receipt.json", receipt)
    print(json.dumps(receipt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
