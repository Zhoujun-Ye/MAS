"""Small data contracts shared by external research benchmarks."""

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
import subprocess


def safe_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value):
        raise ValueError("Invalid task/database identifier")
    return value


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def verify_sources(root, benchmark):
    """Verify loader/evaluator inputs against Git, not just the HEAD label."""
    root = Path(root)
    scopes = {"dataclawbench": ["dataclaw", "assets/qa_raw"],
              "hybriddeepresearch": ["evaluation"],
              "fdabench": ["FDABench/evaluation", "FDABench/utils/test_utils.py",
                           "FDABench/utils/database_connection_manager.py"]}[benchmark]
    raw = subprocess.check_output(["git", "-C", str(root), "ls-tree", "-r", "-z", "HEAD", "--", *scopes])
    expected = set()
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        metadata, encoded_path = entry.split(b"\t", 1)
        mode, kind, oid = metadata.decode().split()
        relative = encoded_path.decode()
        if Path(relative).suffix not in {".py", ".txt", ".json"}:
            continue
        expected.add(relative)
        path = root / relative
        if mode not in {"100644", "100755"} or kind != "blob" or path.is_symlink() or not path.is_file():
            raise ValueError("Missing or nonregular pinned source: " + relative)
        content = path.read_bytes()
        actual = hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest()
        if actual != oid:
            raise ValueError("Source differs from pinned Git content: " + relative)
    actual = {str(p.relative_to(root)) for scope in scopes
              for p in ([root / scope] if (root / scope).is_file() else (root / scope).rglob("*"))
              if p.suffix in {".py", ".txt", ".json"} and (p.is_file() or p.is_symlink())}
    if not expected or actual != expected:
        raise ValueError("Pinned source inventory is incomplete or contains extra inputs")


def jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path, rows, *, replace=False):
    path = Path(path)
    if path.exists() and not replace:
        raise FileExistsError(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
    temporary.replace(path)


@dataclass(frozen=True)
class Task:
    id: str
    benchmark: str
    question: str
    category: str
    web: bool
    source_sha256: str
    db: str | None = None
    # Never serialize this object wholesale into an agent-visible workspace.
    reference: dict = field(default_factory=dict, repr=False)

    def public(self):
        return dict(id=self.id, benchmark=self.benchmark, question=self.question,
                    category=self.category, web=self.web, db=self.db,
                    source_sha256=self.source_sha256)


def unique(tasks):
    if not tasks or len({t.id for t in tasks}) != len(tasks):
        raise ValueError("Expected nonempty tasks with unique IDs")
    return tasks


def predictions(path, tasks):
    rows = jsonl(path)
    ids = [row["instance_id"] for row in rows]
    expected = {task.id for task in tasks}
    if len(ids) != len(set(ids)) or set(ids) != expected:
        raise ValueError("Predictions must cover selected IDs exactly, including failed attempts")
    for row in rows:
        if not isinstance(row.get("final_answer"), str):
            raise ValueError("final_answer must be text; use empty text for a failed attempt")
    return {row["instance_id"]: row for row in rows}


def asset_manifest(root, *, hash_file=digest):
    root = Path(root).resolve(strict=True)
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Input asset symlinks are not allowed")
        if path.is_file():
            with path.open("rb") as stream:
                if stream.read(80).startswith(b"version https://git-lfs.github.com/spec/"):
                    raise ValueError("Git LFS pointer is not a hydrated input asset: " + str(path))
            files[str(path.relative_to(root))] = hash_file(path)
    if not files:
        raise ValueError("Input asset directory is empty")
    return files
