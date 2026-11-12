"""Native observations and explicit Single/mandatory-delegation permissions."""

import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import sys

# Claude Code 2.1.286 removed TaskOutput; listing it would only name a missing tool.
SINGLE_TOOLS = ("Bash", "Read", "Write", "Edit", "Glob", "Grep", "NotebookEdit",
                "TaskCreate", "TaskUpdate", "TaskGet", "TaskList", "TaskStop")
SUBAGENT_TOOLS = (*SINGLE_TOOLS, "Agent", "Task", "SendMessage", "ListAgents")
BLOCKED_TOOLS = ("Agent", "Task", "SendMessage", "ListAgents", "Workflow", "CronCreate", "CronDelete",
                 "CronList", "ScheduleWakeup")
DELEGATION_POLICY = dict(version='native-delegation-v1', minimum_workers=1,
    initial_tools=['Read', 'Glob', 'Grep', 'TaskCreate', 'TaskUpdate', 'TaskGet', 'TaskList', 'Agent', 'Task'],
    unlock='root Agent/Task call followed by matching native SubagentStart',
    stop='block until native worker start', scope='structural delegation, not semantic contribution')
DELEGATION_REASON = ('Delegate a substantive part of the task using the native Agent tool before '
    'running commands, writing files or finishing. Read-only inspection and task planning remain '
    'available. After a worker starts, continue your own work and synthesize its results.')


def delegation_tool(name):
    return name in BLOCKED_TOOLS or "subagent" in name.lower()


def single_decision(payload):
    if payload.get("hook_event_name") == "PreToolUse" and delegation_tool(str(payload.get("tool_name", ""))):
        return dict(hookSpecificOutput=dict(hookEventName="PreToolUse", permissionDecision="deny",
            permissionDecisionReason="Strict single-agent condition: delegation and peer coordination are disabled."))
    if payload.get("hook_event_name") == "SubagentStart":
        return {"continue": False, "stopReason": "Strict single-agent condition violated: unexpected worker"}
    return {}


def required_delegation_decision(payload, state):
    """A native worker start, not an attempted call or internal agent stop, unlocks work."""
    event = payload.get('hook_event_name')
    session = payload.get('session_id')
    if not isinstance(session, str) or not session:
        raise ValueError('Missing native session identity')
    sessions = state.setdefault('sessions', {})
    if event == 'SessionStart':
        sessions.setdefault(session, dict(pending={}, started=[]))
    current = sessions[session]
    pending, started = current['pending'], current['started']
    if not isinstance(pending, dict) or not isinstance(started, list):
        raise ValueError('Invalid mandatory delegation state')
    worker = bool(payload.get('agent_id') or payload.get('agentId') or
                  '/subagents/' in str(payload.get('transcript_path', '')))
    tool, call = payload.get('tool_name'), payload.get('tool_use_id')
    decision, action = {}, 'observed'
    if event == 'SubagentStart' and payload.get('agent_id') and payload.get('agent_type'):
        matching = next((key for key, value in pending.items()
            if (value.get('type') if isinstance(value, dict) else value) == payload['agent_type']
            and (not isinstance(value, dict) or value.get('agent_id') == payload['agent_id'])), None)
        if matching is not None:
            pending.pop(matching)
            if payload['agent_id'] not in started:
                started.append(payload['agent_id'])
            action = 'worker_started'
    elif not worker and event == 'PreToolUse':
        if tool in {'Agent', 'Task'} and isinstance(call, str) and call:
            inputs = payload.get('tool_input') or {}
            pending[call] = inputs.get('subagent_type', 'general-purpose')
        elif not started and tool not in DELEGATION_POLICY['initial_tools']:
            decision = dict(hookSpecificOutput=dict(hookEventName='PreToolUse',
                permissionDecision='deny', permissionDecisionReason=DELEGATION_REASON))
            action = 'tool_denied'
    elif not worker and event in {'PostToolUse', 'PostToolUseFailure'} and tool in {'Agent', 'Task'}:
        response = payload.get('tool_response')
        identity = (response.get('agentId') or response.get('agent_id')) if isinstance(response, dict) else None
        if (event == 'PostToolUse' and call in pending and identity
                and response.get('status') in {'async_launched', 'completed'}):
            # Async Agent returns can precede SubagentStart; retain the exact identity join.
            value = pending[call]
            pending[call] = dict(type=value.get('type') if isinstance(value, dict) else value, agent_id=identity)
        else:
            pending.pop(call, None)
    elif not worker and event == 'Stop' and not started:
        decision = dict(decision='block', reason=DELEGATION_REASON)
        action = 'stop_blocked'
    payload['mandatory_delegation'] = dict(version=DELEGATION_POLICY['version'], action=action,
                                          started_worker_ids=list(started))
    return decision


def delegation_state(path, payload):
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        if payload.get('hook_event_name') != 'SessionStart':
            raise ValueError('Mandatory delegation state missing before native session start') from None
        return dict(sessions={})
    with os.fdopen(descriptor) as stream:
        value = json.load(stream)
    if not isinstance(value, dict) or not isinstance(value.get('sessions'), dict):
        raise ValueError('Invalid mandatory delegation state')
    return value


def save_delegation_state(path, value):
    temporary = path.with_suffix('.tmp')
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(descriptor, 'w') as stream:
            json.dump(value, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    policy = parser.add_mutually_exclusive_group()
    policy.add_argument("--single-agent", action="store_true")
    policy.add_argument('--require-delegation', action='store_true')
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
        decision = single_decision(payload) if args.single_agent else {}
        if args.require_delegation:
            try:
                path = args.output.parent/'delegation-state.json'
                state = delegation_state(path, payload)
                decision = required_delegation_decision(payload, state)
                save_delegation_state(path, state)
            except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
                payload['mandatory_delegation'] = dict(version=DELEGATION_POLICY['version'],
                    action='policy_error', error_type=type(error).__name__, started_worker_ids=[])
                decision = {'continue': False, 'stopReason': 'Mandatory delegation policy state unavailable; stopping.'}
        stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
        stream.flush()
    print(json.dumps(decision))


if __name__ == "__main__":
    main()
