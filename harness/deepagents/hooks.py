"""Dcode's native hook protocol: record evidence and deny delegation, no SDK."""

import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import sys


def delegation_tool(name):
    return name in {"task", "Agent", "Task"} or "subagent" in name.lower() or name.endswith("_async_task")


def decision(payload):
    blocked = delegation_tool(str(payload.get("tool_name", "")))
    if payload.get("hook_event_name") == "PreToolUse" and blocked:
        return dict(hookSpecificOutput=dict(hookEventName="PreToolUse", permissionDecision="deny",
            permissionDecisionReason="Strict single-agent experiment: delegation is disabled. Solve directly using file and shell tools."))
    if payload.get("hook_event_name") == "SubagentStart":
        return {"continue": False, "stopReason": "Single-agent condition violated: unexpected subagent start"}
    return {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = json.load(sys.stdin)
    payload["observer_received_at"] = datetime.now(timezone.utc).isoformat()
    payload["single_policy_blocked"] = delegation_tool(str(payload.get("tool_name", "")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
    print(json.dumps(decision(payload)))


if __name__ == "__main__":
    main()
