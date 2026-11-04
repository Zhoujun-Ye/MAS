"""Delete named Codex artifacts only; retain Claude files and filter mixed indexes."""

import argparse
import json
from pathlib import Path
import shutil

from benchmarks._io import write_json


INDEXES = {"summary.json", "progress.json", "grading-progress.json", "authorization.json",
           "comparison.json", "comparison-updated.json"}
REMOVED = object()


def codex_path(value):
    return isinstance(value, str) and any(part.startswith("codex-") for part in Path(value).parts)


def filter_index(value):
    if isinstance(value, dict):
        if str(value.get("backend", "")).startswith("codex-") or codex_path(value.get("source")):
            return REMOVED
        result = {}
        for key, item in value.items():
            if key.startswith("codex-"):
                continue
            filtered = filter_index(item)
            if filtered is not REMOVED:
                result[key] = filtered
        return result
    if isinstance(value, list):
        return [filtered for item in value if (filtered := filter_index(item)) is not REMOVED]
    return value


def clean(root, *, execute=False):
    root = Path(root).resolve(strict=True)
    paths, updates = [], []
    for path in sorted(root.rglob("*"), key=lambda p: len(p.parts)):
        if any(parent == path or parent in path.parents for parent in paths):
            continue
        if path.is_symlink():
            continue
        if path.name.startswith("codex-") or "-codex-" in path.name:
            paths.append(path)
            continue
        if path.is_file() and (path.name in INDEXES or path.name.startswith("recovered-")) and path.suffix == ".json":
            original = json.loads(path.read_text())
            filtered = filter_index(original)
            if filtered is REMOVED:
                paths.append(path)
            elif original != filtered:
                updates.append((path, filtered))
    for path, data in updates:
        if any(parent in path.parents for parent in paths):
            continue
        if isinstance(data, dict):
            data["retired_results"] = "Codex entries removed by user request. Shared-account balances may include retired runs; not Claude-only billing. Original frozen per-Claude plans and raw evidence are unchanged."
        if execute:
            write_json(path, data)
    if execute:
        for path in paths:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
    return dict(root=str(root),executed=execute,deleted=[str(p) for p in paths],
                filtered_indexes=[str(p) for p, _ in updates])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    print(json.dumps(clean(args.root, execute=args.execute), indent=2))


if __name__ == "__main__":
    main()
