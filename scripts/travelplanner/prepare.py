#!/usr/bin/env python3
"""Download pinned public inputs only. No credentials or model calls."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.request

CODE = "e52c87f4ac348a3410c46dc3553c519db5ec5e23"
ENV = "f2183898e2b9547ed2a6f5356ae4cbc3f3431bf4"
DATA = "8736504ecfc31b7f8b7e40122873c337e83fff7c"
DATABASE = (
    "accommodations/clean_accommodations_2022.csv", "attractions/attractions.csv",
    "background/citySet.txt", "background/citySet_with_states.txt", "background/stateSet.txt",
    "flights/clean_Flights_2022.csv", "googleDistanceMatrix/distance.csv",
    "restaurants/clean_restaurant_2022.csv",
)
SOURCES = ("README.md", "LICENSE", "utils/func.py",
           "evaluation/commonsense_constraint.py", "evaluation/hard_constraint.py") + tuple(
    f"tools/{name}/apis.py" for name in
    ("flights", "accommodations", "restaurants", "attractions", "googleDistanceMatrix"))


def fetch(url, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=120) as response, temporary.open("wb") as out:
                while chunk := response.read(1024 * 1024):
                    out.write(chunk)
            temporary.replace(path)
            return
        except Exception:
            temporary.unlink(missing_ok=True)
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)


def hashes(path):
    size = path.stat().st_size
    sha, blob = hashlib.sha256(), hashlib.sha1(f"blob {size}\0".encode())
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            sha.update(chunk)
            blob.update(chunk)
    return size, sha.hexdigest(), blob.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hf-endpoint", default="https://hf-mirror.com")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2] / "benchmarks/travelplanner"
    manifest_path = root / "assets/prepared.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        for item in manifest["files"]:
            size, sha, _ = hashes(root / item["path"])
            if size != item["bytes"] or sha != item["sha256"]:
                raise ValueError(f"Prepared data changed: {item['path']}")
        print(json.dumps({"status": "verified", "files": len(manifest["files"])}))
        return
    files = []

    def add(relative, url, expected=None):
        path = root / relative
        if not path.exists():
            fetch(url, path)
        size, sha, blob = hashes(path)
        if expected:
            expected_hash = expected.get("lfs", {}).get("oid") or expected["oid"]
            actual = sha if "lfs" in expected else blob
            if size != expected["size"] or actual != expected_hash:
                raise ValueError(f"Remote content hash mismatch: {relative}")
        files.append(dict(path=relative, bytes=size, sha256=sha, url=url))
        print(f"verified {relative}: {size} bytes", flush=True)

    for name in SOURCES:
        add(f"upstream/{name}", f"https://raw.githubusercontent.com/OSU-NLP-Group/TravelPlanner/{CODE}/{name}")
    base = args.hf_endpoint.rstrip("/")
    trees = {}
    for name in DATABASE:
        directory = name.split("/")[0]
        if directory not in trees:
            url = f"{base}/api/spaces/osunlp/TravelPlannerEnvironment/tree/{ENV}/database/{directory}"
            with urllib.request.urlopen(url, timeout=120) as response:
                trees[directory] = {r["path"]: r for r in json.load(response)}
        add(f"assets/database/{name}",
            f"{base}/spaces/osunlp/TravelPlannerEnvironment/resolve/{ENV}/database/{name}",
            trees[directory][f"database/{name}"])
    with urllib.request.urlopen(f"{base}/api/datasets/osunlp/TravelPlanner/tree/{DATA}", timeout=120) as response:
        entry = next(r for r in json.load(response) if r["path"] == "validation.csv")
    add("assets/validation.csv", f"{base}/datasets/osunlp/TravelPlanner/resolve/{DATA}/validation.csv", entry)
    link = root / "upstream/database"
    if not link.exists():
        os.symlink("../assets/database", link, target_is_directory=True)
    manifest = dict(code_revision=CODE, environment_revision=ENV, dataset_revision=DATA,
                    split="validation", files=files, total_bytes=sum(f["bytes"] for f in files),
                    paid_calls=0, headroom="unmeasured")
    with manifest_path.open("x") as output:
        json.dump(manifest, output, indent=2)
    print(json.dumps({k: v for k, v in manifest.items() if k != "files"}))


if __name__ == "__main__":
    main()
