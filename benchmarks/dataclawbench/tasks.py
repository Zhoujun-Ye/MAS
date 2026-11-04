"""Read upstream QA JSON, never expose generated task markdown (it embeds gold)."""

import json
from pathlib import Path

from .._external import Task, digest, safe_id, unique

UPSTREAM = "https://github.com/GTML-LAB-sysu/DataClaw"
REVISION = "32e138750ceba41b47290211403ad1781d5e1971"


def load_tasks(root):
    root = Path(root)
    tasks = []
    for index, path in enumerate(sorted((root / "assets/qa_raw").rglob("*_result.json")), 1):
        data = json.loads(path.read_text(encoding="utf-8"))
        for key in ("id", "question", "guidelines", "answer"):
            if key not in data:
                raise ValueError(f"Missing DataClaw field: {key}")
        if any(not isinstance(data[k], str) or not data[k].strip() for k in ("question", "guidelines")):
            raise ValueError("Question and output guidelines must be nonempty text")
        category = str(data.get("metadata", {}).get("category", path.parent.name))
        level = str(data.get("metadata", {}).get("level", "unknown"))
        slug = lambda s: "".join(c if c.isalnum() else "_" for c in s.lower()).strip("_")
        identity = safe_id(f"task_{index:03d}_{slug(category)}_{slug(level)}_{slug(str(data['id']))}")
        web = category == "international_comparison"
        access = "You may use files under ./database/ and web search." if web else "Only use files under ./database/."
        question = data["question"].strip() + "\n\nOutput guidelines:\n" + data["guidelines"].strip() + "\n\n" + access
        tasks.append(Task(identity, "dataclawbench", question, category, web, digest(path), reference=data))
    return unique(tasks)
