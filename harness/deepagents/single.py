"""Native dcode command-hook policy for the explicit single-agent condition."""

import hashlib
import json
from pathlib import Path
import shlex

EVENTS = ("SessionStart", "SessionEnd", "PreToolUse", "PostToolUse", "SubagentStart", "SubagentStop")


def prepare_profile(profile, *, script, observer, python="python3"):
    profile = Path(profile)
    profile.mkdir(parents=True, exist_ok=True)
    command = shlex.join([python, "-I", str(script), "--output", str(observer)])
    policy = dict(hooks={event: [dict(matcher=".*", hooks=[dict(type="command", command=command)])]
                         for event in EVENTS})
    with (profile / "hooks.json").open("x") as stream:
        json.dump(policy, stream, indent=2)
    with (profile / "single-policy.json").open("x") as stream:
        json.dump(dict(hooks_sha256=hashlib.sha256((profile / "hooks.json").read_bytes()).hexdigest(),
                       script_sha256=hashlib.sha256(Path(__file__).with_name("hooks.py").read_bytes()).hexdigest(),
                       native_command=command, policy="deny synchronous and asynchronous delegation"), stream)
    return validate_profile(profile)


def validate_profile(profile):
    profile = Path(profile)
    receipt = json.loads((profile / "single-policy.json").read_text())
    if hashlib.sha256((profile / "hooks.json").read_bytes()).hexdigest() != receipt["hooks_sha256"]:
        raise ValueError("Native single-agent hook policy changed")
    if hashlib.sha256(Path(__file__).with_name("hooks.py").read_bytes()).hexdigest() != receipt["script_sha256"]:
        raise ValueError("Single-agent hook executable changed")
    return receipt


def audit_events(path):
    path = Path(path)
    events = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
    kinds = [event.get("hook_event_name") for event in events]
    started = [e for e in events if e.get("hook_event_name") == "SubagentStart"]
    delegated = [e for e in events if e.get("hook_event_name") == "PostToolUse"
                 and e.get("single_policy_blocked")]
    return dict(passed="SessionStart" in kinds and "SessionEnd" in kinds and not started and not delegated,
                session_start_observed="SessionStart" in kinds, session_end_observed="SessionEnd" in kinds,
                subagent_starts=len(started), executed_delegation_tools=len(delegated),
                denied_delegation_attempts=sum(e.get("hook_event_name") == "PreToolUse"
                    and e.get("single_policy_blocked", False) for e in events), event_count=len(events))
