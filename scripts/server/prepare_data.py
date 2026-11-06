"""Explicit, hash-checked external data hydration; no model or judge calls."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from benchmarks._external import digest
from common.io import write_json
from benchmarks.dataclawbench.tasks import REVISION as DC_REVISION

HDR_RELEASE = "31304784b7aec82f22d59772a8afeb78567fd8b3"
HDR_DATABASES = "0664a2f28555faa0dd2947c8c23288df79bcc06b"


def download(url, path, *, sha256=None, git_blob=None, size=None):
    path = Path(path)
    def valid(candidate):
        if not candidate.is_file() or candidate.is_symlink():
            return False
        if size is not None and candidate.stat().st_size != size:
            return False
        if sha256 and digest(candidate) != sha256:
            return False
        if git_blob:
            content = candidate.read_bytes()
            if hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest() != git_blob:
                return False
        return bool(sha256 or git_blob)
    if not valid(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_suffix(path.suffix + ".part")
        subprocess.run(["curl", "--fail", "--location", "--silent", "--show-error",
                        "--max-time", "180", "--output", str(partial), url], check=True)
        if not valid(partial):
            raise ValueError("Downloaded asset failed integrity check: " + str(path))
        partial.replace(path)
    return dict(bytes=path.stat().st_size, sha256=digest(path), source=url)


def hf_files(endpoint, repository, revision):
    url = f"{endpoint}/api/datasets/{repository}/tree/{revision}?recursive=true&limit=1000"
    with urllib.request.urlopen(url, timeout=60) as response:
        if response.headers.get("Link"):
            raise ValueError("Dataset pagination requires explicit handling before downloading")
        return [item for item in json.load(response) if item["type"] == "file"]


def prepare(root, endpoint):
    receipts = {}
    upstream = root / "dataclawbench/upstream"
    revision = subprocess.check_output(["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True).strip()
    if revision != DC_REVISION:
        raise ValueError("DataClaw checkout does not match pin")
    paths = subprocess.check_output(["git", "-C", str(upstream), "ls-tree", "-r", "--name-only", "HEAD", "assets/database"], text=True)
    for relative in paths.splitlines():
        original = subprocess.check_output(["git", "-C", str(upstream), "show", f"HEAD:{relative}"])
        if original.startswith(b"version https://git-lfs.github.com/spec/"):
            pointer = dict(line.split(" ", 1) for line in original.decode().splitlines())
            url = f"https://media.githubusercontent.com/media/GTML-LAB-sysu/DataClaw/{revision}/{urllib.parse.quote(relative)}"
            receipts["dataclawbench/" + relative] = download(url, upstream / relative,
                sha256=pointer["oid"].removeprefix("sha256:"), size=int(pointer["size"]))
    for repository, revision, prefix in (
            ("Snowflake/HybridDeepResearch", HDR_RELEASE, "hybriddeepresearch/release"),
            ("birdsql/livesqlbench-base-lite-sqlite", HDR_DATABASES, "hybriddeepresearch/data")):
        for item in hf_files(endpoint, repository, revision):
            relative = item["path"]
            selected = (relative == "hybrid_ds_release/hybrid_ds_release.jsonl" if "release" in prefix
                        else relative.endswith(("_template.sqlite", "_kb.jsonl")))
            if not selected:
                continue
            if Path(relative).is_absolute() or ".." in Path(relative).parts:
                raise ValueError("Unsafe dataset path")
            lfs = item.get("lfs", {})
            url = f"{endpoint}/datasets/{repository}/resolve/{revision}/{urllib.parse.quote(relative)}?download=true"
            receipts[prefix + "/" + relative] = download(url, root / prefix / relative,
                sha256=lfs.get("oid"), git_blob=None if lfs else item["oid"], size=item["size"])
    return dict(files=receipts, hydrated_files=len(receipts), paid_calls=0,
                hdr_release_revision=HDR_RELEASE, hdr_databases_revision=HDR_DATABASES)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--hf-endpoint", default="https://huggingface.co")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps(dict(status="planned", root=str(args.root), paid_calls=0)))
        return
    os.umask(0o077)
    receipt = prepare(args.root.resolve(), args.hf_endpoint.rstrip("/"))
    write_json(args.root / "receipts/data-hydration.json", receipt)
    print(json.dumps(dict(status="prepared", hydrated_files=receipt["hydrated_files"], paid_calls=0)))


if __name__ == "__main__":
    main()
