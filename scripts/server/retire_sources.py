"""Remove the explicitly retired server modules after a private source-only snapshot."""

import argparse
import os
from pathlib import Path
import shutil
import tarfile


FILES = (
    "harness/claude_code_agent_team/__init__.py", "harness/claude_code_agent_team/cli.py",
    "harness/claude_code_agent_team/terminal.py", "harness/deepagents/__init__.py",
    "harness/deepagents/cli.py", "harness/deepagents/hooks.py", "harness/deepagents/single.py",
    "scripts/probes/agent_team.py", "tests/test_claude_terminal.py", "tests/test_deepagents_single.py",
    "benchmarks/kramabench/_io.py", "scripts/kramabench/cli_preflight.py",
    "scripts/kramabench/claude_single_native_probe.py", "scripts/kramabench/single_native_probe.py",
    "scripts/kramabench/subagents_native_probe.py", "scripts/kramabench/native_evidence.py",
    "scripts/kramabench/compare_claude_single.py", "scripts/kramabench/compare_subagents.py",
    "scripts/kramabench/scoped_subagents_pilot.py",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    root = args.repo.resolve()
    paths = [p for p in FILES if (root / p).is_file() and not (root / p).is_symlink()]
    if args.execute and paths:
        os.umask(0o077)
        archive = root / "archives/engineering-cleanup-20261104/retired-source.tgz"
        archive.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive, "x:gz") as saved:
            for name in paths:
                saved.add(root / name, arcname=name, recursive=False)
        for name in paths:
            (root / name).unlink()
        for relative in ("harness/claude_code_agent_team", "harness/deepagents"):
            folder = root / relative
            cache = folder / "__pycache__"
            if cache.is_dir() and not cache.is_symlink():
                shutil.rmtree(cache)
            if folder.is_dir() and not any(folder.iterdir()):
                folder.rmdir()
    print(dict(executed=args.execute, source_files=len(paths), names=paths))


if __name__ == "__main__":
    main()
