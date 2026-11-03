"""Native Claude observations, with an opt-in strict-single permission guard."""

import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import sys

SINGLE_TOOLS = ("Bash", "Read", "Write", "Edit", "Glob", "Grep", "NotebookEdit",
                "TaskCreate", "TaskUpdate", "TaskGet", "TaskList", "TaskOutput", "TaskStop")
BLOCKED_TOOLS = ("Agent", "Task", "SendMessage", "Workflow", "CronCreate", "CronDelete",
                 "CronList", "ScheduleWakeup")


def delegation_tool(name):
    return name in BLOCKED_TOOLS or "subagent" in name.lower()


def single_decision(payload):
    if payload.get("hook_event_name") == "PreToolUse" and delegation_tool(str(payload.get("tool_name", ""))):
        return dict(hookSpecificOutput=dict(hookEventName="PreToolUse", permissionDecision="deny",
            permissionDecisionReason="Strict single-agent condition: delegation and peer coordination are disabled."))
    if payload.get("hook_event_name") == "SubagentStart":
        return {"continue": False, "stopReason": "Strict single-agent condition violated: unexpected worker"}
    return {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--single-agent", action="store_true")
    args = parser.parse_args()
    payload = json.load(sys.stdin)
    payload["observer_received_at"] = datetime.now(timezone.utc).isoformat()
    if args.single_agent:
        payload["single_agent_policy"] = True
        payload["single_policy_blocked"] = (payload.get("hook_event_name") == "PreToolUse"
                                             and delegation_tool(str(payload.get("tool_name", ""))))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
        stream.flush()
    print(json.dumps(single_decision(payload) if args.single_agent else {}))


if __name__ == "__main__":
    main()
