"""Archive explicitly selected results reversibly; never delete output roots."""

import argparse
import json
from pathlib import Path
import uuid


def targets(repo, selected):
    root = repo.resolve() / "outputs/current"
    paths = []
    for name in selected:
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise ValueError("Select a named result below outputs/current")
        path = root / relative
        if path == root or path.is_symlink() or path.resolve() != path or not path.is_dir():
            raise ValueError("Target must be an existing non-symlink result directory")
        if any(path == p or path in p.parents or p in path.parents for p in paths):
            raise ValueError("Overlapping targets")
        paths.append(path)
    return paths


def archive(repo, selected):
    paths = targets(repo, selected)
    destination = repo.resolve() / "archives" / ("explicit-results-" + uuid.uuid4().hex)
    if destination.parent.is_symlink():
        raise ValueError("Archive root must not be a symlink")
    destination.mkdir(parents=True, exist_ok=False)
    for path in paths:
        target = destination / path.relative_to(repo.resolve() / "outputs/current")
        target.parent.mkdir(parents=True, exist_ok=True)
        path.rename(target)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--target", action="append", required=True,
                        help="Exact result directory relative to outputs/current; repeat explicitly")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    paths = targets(args.repo, args.target)
    destination = archive(args.repo, args.target) if args.execute else None
    print(json.dumps(dict(deleted=False, archived=args.execute,
        snapshot=str(destination) if destination else None, paths=[str(p) for p in paths]), indent=2))


if __name__ == "__main__":
    main()
