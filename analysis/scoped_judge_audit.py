"""Measure observable delegation scope and timing, without model calls."""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import statistics


def seconds(start, end):
    if not start or not end:
        return None
    return (datetime.fromisoformat(end.replace("Z", "+00:00")) -
            datetime.fromisoformat(start.replace("Z", "+00:00"))).total_seconds()


def read(path):
    raw = path.read_bytes()
    records = []
    for line, text in enumerate(raw.decode().splitlines(), 1):
        item = json.loads(text)
        message = item.get("message", {})
        content = message.get("content", [])
        if isinstance(content, str):
            content = [dict(type="text", text=content)]
        blocks = [b for b in content if b.get("type") != "thinking"]
        if blocks:
            records.append(dict(line=line, timestamp=item.get("timestamp"),
                                role=message.get("role"), blocks=blocks))
    return records, hashlib.sha256(raw).hexdigest()


def inspect(root, task):
    profiles = root / task / "claude-code-subagents/native-profile/claude/projects"
    parent_paths = sorted(profiles.glob("*/*.jsonl"))
    children = []
    delegation = []
    parent_first = None
    write_submission = None
    for path in parent_paths:
        records, _ = read(path)
        if records:
            parent_first = min(parent_first or records[0]["timestamp"], records[0]["timestamp"])
        seen = set()
        for record in records:
            for b in record["blocks"]:
                if b.get("type") != "tool_use" or b["id"] in seen:
                    continue
                seen.add(b["id"])
                if b.get("name") in ("Agent", "Task"):
                    delegation.append(dict(timestamp=record["timestamp"], line=record["line"],
                        source=str(path), description=b.get("input", {}).get("description"),
                        tool_id=b["id"], input=b.get("input", {})))
                if b.get("name") == "Write" and str(b.get("input", {}).get("file_path", "")).endswith("/submission.json"):
                    write_submission = min(write_submission or record["timestamp"], record["timestamp"])
    for path in sorted(profiles.glob("*/*/subagents/*.jsonl")):
        records, sha = read(path)
        if not records:
            continue
        tools, seen, prompts, turns, tool_records = Counter(), set(), [], [], []
        final_text, final_time, final_line = "", None, None
        for record in records:
            texts = "\n".join(b["text"] for b in record["blocks"] if b.get("type") == "text")
            if record["role"] == "user" and texts:
                if turns:
                    turns[-1].update(return_words=len(final_text.split()), return_line=final_line)
                prompts.append(dict(line=record["line"], timestamp=record["timestamp"], text=texts))
                turns.append(dict(tool_calls=0, prompt_words=len(texts.split())))
                final_text = ""
            for b in record["blocks"]:
                if b.get("type") == "tool_use" and b["id"] not in seen:
                    seen.add(b["id"])
                    tools[b["name"]] += 1
                    tool_records.append(dict(line=record["line"], timestamp=record["timestamp"],
                        name=b["name"], input=b.get("input", {})))
                    if turns:
                        turns[-1]["tool_calls"] += 1
            if record["role"] == "assistant" and texts:
                final_text, final_time, final_line = texts, record["timestamp"], record["line"]
        if turns:
            turns[-1].update(return_words=len(final_text.split()), return_line=final_line)
        children.append(dict(source=str(path), sha256=sha, tools=dict(tools), tool_records=tool_records, turns=turns,
            prompt_words=len(prompts[0]["text"].split()) if prompts else None,
            prompt_chars=len(prompts[0]["text"]) if prompts else None,
            received_prompts=prompts, final_text=final_text, final_line=final_line,
            first_message=records[0]["timestamp"], final_text_time=final_time,
            observed_seconds=seconds(records[0]["timestamp"], final_time),
            before_first_explicit_submission_write=(final_time <= write_submission if final_time and write_submission else None)))
    return dict(task_id=task, parent_first=parent_first, delegation=delegation, children=children,
        first_dispatch_seconds=seconds(parent_first, min((d["timestamp"] for d in delegation), default=None)),
        first_explicit_submission_write=write_submission)


def aggregate(rows):
    children = [c for r in rows for c in r["children"]]
    turns = [t for c in children for t in c["turns"]]
    def median(values):
        values = [v for v in values if v is not None]
        return statistics.median(values) if values else None
    return dict(tasks=len(rows), child_transcripts=len(children), child_turns=len(turns),
        root_delegation_calls=sum(len(r["delegation"]) for r in rows),
        median_child_observed_seconds=median([c["observed_seconds"] for c in children]),
        median_first_dispatch_seconds=median([r["first_dispatch_seconds"] for r in rows]),
        median_child_prompt_words=median([c["prompt_words"] for c in children]),
        median_child_prompt_chars=median([c["prompt_chars"] for c in children]),
        median_child_return_words=median([t["return_words"] for t in turns]),
        median_tool_calls_per_turn=median([t["tool_calls"] for t in turns]),
        turns_with_at_most_3_tools=sum(t["tool_calls"] <= 3 for t in turns),
        turns_with_at_most_250_return_words=sum(t["return_words"] <= 250 for t in turns),
        zero_tool_turns=sum(t["tool_calls"] == 0 for t in turns),
        child_tool_calls=sum(sum(c["tools"].values()) for c in children),
        child_before_explicit_submission_write=sum(c["before_first_explicit_submission_write"] is True for c in children),
        submission_write_timing_coverage=sum(c["before_first_explicit_submission_write"] is not None for c in children))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--old-root", type=Path, required=True)
    parser.add_argument("--new-root", type=Path, required=True)
    args = parser.parse_args()
    task_ids = json.loads(args.selection.read_text())["task_ids"]
    old = [inspect(args.old_root, task) for task in task_ids]
    new = [inspect(args.new_root, task) for task in task_ids]
    print(json.dumps(dict(old=aggregate(old), new=aggregate(new), old_tasks=old, new_tasks=new,
        scope="Observable messages only. Child interval excludes time before first retained message; not a cold-start measure. Final text is not necessarily the only delivered communication. Word counts use whitespace. Explicit submission Write is an artifact-timing proxy, not psychological commitment. Tool-call counts do not establish narrow search scope or correctness."), indent=2))


if __name__ == "__main__":
    main()
