"""Read only public questions from a pinned upstream workload."""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import subprocess

UPSTREAM_URL = "https://github.com/mitdbg/Kramabench.git"
UPSTREAM_COMMIT = "b2e0d77540263f8b6119f977fe79a8c4386b5a02"
DOMAINS = ("archeology", "astronomy", "biomedical", "environment", "legal", "wildfire")


@dataclass(frozen=True)
class Task:
    id: str
    domain: str
    query: str

    def __post_init__(self):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", self.id) or self.domain not in DOMAINS or not self.query.strip():
            raise ValueError("Invalid public task")


def public_tasks(rows, domain):
    # Gold answers, types, reference subsets and subtasks never enter Task.
    tasks = [Task(row["id"], domain, row["query"]) for row in rows]
    if len({task.id for task in tasks}) != len(tasks):
        raise ValueError("Duplicate task IDs")
    return tasks


def load_tasks(upstream):
    root = Path(upstream)
    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args])
    if git("rev-parse", "HEAD").decode().strip() != UPSTREAM_COMMIT:
        raise ValueError("Unexpected KramaBench revision")
    tasks, hashes = [], {}
    for domain in DOMAINS:
        relative = f"workload/{domain}.json"
        data = (root / relative).read_bytes()
        if data != git("show", f"{UPSTREAM_COMMIT}:{relative}"):
            raise ValueError(f"Modified workload: {relative}")
        hashes[relative] = hashlib.sha256(data).hexdigest()
        tasks.extend(public_tasks(json.loads(data), domain))
    if len({t.id for t in tasks}) != len(tasks):
        raise ValueError("Duplicate cross-domain IDs")
    return tasks, {"repository": UPSTREAM_URL, "commit": UPSTREAM_COMMIT, "workload_sha256": hashes}
