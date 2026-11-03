"""Read retained native Claude transcripts without running an agent or judge.

Print JSONL with source line anchors. With --task, include ordinary tool records;
otherwise emit only original questions and delegation requests/results.
"""

import argparse
import hashlib
import json
from pathlib import Path


def records(path):
    with path.open() as handle:
        for line, raw in enumerate(handle, 1):
            item = json.loads(raw)
            message = item.get("message", {})
            content = message.get("content", [])
            attachment = item.get("attachment", {})
            if (attachment.get("type") == "queued_command" and
                    "<task-notification>" in attachment.get("prompt", "")):
                content = [{"type": "text", "text": attachment["prompt"]}]
            if isinstance(content, str):
                content = [{"type": "text", "text": content}]
            blocks = [b for b in content if b.get("type") != "thinking"]
            if blocks:
                yield dict(source=str(path), line=line, role=message.get("role"),
                           native_attachment_type=attachment.get("type"),
                           uuid=item.get("uuid"), parent_uuid=item.get("parentUuid"),
                           timestamp=item.get("timestamp"), blocks=blocks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--task", action="append", default=[])
    args = parser.parse_args()
    summary = json.loads((args.root / "summary.json").read_text())
    for row in summary["rows"]:
        task = row["task_id"]
        if args.task and task not in args.task:
            continue
        root = args.root / task / row["backend"]
        grade = row.get("effective_grade", row["grade"])
        submission = root / "submission.json"
        submission_bytes = submission.read_bytes()
        submission_sha = hashlib.sha256(submission_bytes).hexdigest()
        if submission.is_symlink() or submission_sha != grade["submission_file_sha256"]:
            raise ValueError(f"Submission no longer matches graded artifact: {task}")
        print(json.dumps(dict(kind="task", task=task,
            question=json.loads((root / "task.json").read_text()),
            submission=json.loads(submission_bytes), submission_sha256=submission_sha,
            artifact_matches_grade=True,
            grade={k: grade.get(k) for k in
                   ("answer_type", "score", "score_kind", "prediction", "target")},
            lifecycle=row.get("subagents_audit")), ensure_ascii=False))
        profiles = root / "native-profile/claude/projects"
        paths = sorted(profiles.glob("*/*.jsonl"))
        if args.task:
            paths += sorted(profiles.glob("*/*/subagents/*.jsonl"))
        for path in paths:
            entries = list(records(path))
            delegation_ids = {b["id"] for r in entries for b in r["blocks"]
                              if b.get("type") == "tool_use" and
                              b.get("name") in ("Agent", "Task", "TaskOutput")}
            print(json.dumps(dict(kind="source", task=task, source=str(path),
                sha256=hashlib.sha256(path.read_bytes()).hexdigest())))
            for entry in entries:
                if not args.task:
                    entry["blocks"] = [b for b in entry["blocks"] if
                        b.get("id") in delegation_ids or
                        b.get("tool_use_id") in delegation_ids or
                        (b.get("type") == "text" and
                         "<task-notification>" in b.get("text", ""))]
                if entry["blocks"]:
                    print(json.dumps(dict(kind="message", task=task, **entry), ensure_ascii=False))


if __name__ == "__main__":
    main()
