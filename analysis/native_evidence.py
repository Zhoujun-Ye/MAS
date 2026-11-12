"""Read native CLI evidence without executing serialized constructors or code."""

import argparse
from collections import Counter
from datetime import datetime
import json
import re
from pathlib import Path


def claude_delegation_tool(name):
    # Keep this evidence reader standalone under the decoder's isolated Python.
    return (name in {"Agent", "Task", "SendMessage", "ListAgents", "Workflow", "CronCreate", "CronDelete", "CronList", "ScheduleWakeup"}
            or "subagent" in name.lower())


def native_surface(folder):
    """Record the actual native init surface; absent fields remain unknown."""
    path = Path(folder) / 'cli/stdout.log'
    for line in path.read_text(errors='replace').splitlines() if path.exists() else ():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get('type') == 'system' and event.get('subtype') == 'init':
            return {key: event.get(key) for key in ('tools', 'skills', 'slash_commands')}
    return dict(tools=None, skills=None, slash_commands=None)


def loop_guard_evidence(folder):
    """Read retained historical intervention counts; never execute a loop detector."""
    path = Path(folder)/'native-profile/observer/events.jsonl'
    by_role = {role: dict(warnings=0, stops=0, errors=0, slow_calls=0) for role in ('lead', 'worker')}
    observed, invalid, notifications, stop_notices, observer_errors = 0, 0, 0, 0, 0
    versions, seen = set(), set()
    if path.is_file() and not path.is_symlink():
        with path.open(encoding='utf-8', errors='replace') as stream:
            for line in stream:
                try:
                    event = json.loads(line)
                    if not isinstance(event, dict):
                        raise ValueError('Invalid native event')
                except (ValueError, UnicodeError):
                    invalid += 1
                    continue
                notice = event.get('loop_worker_notice')
                if isinstance(notice, dict):
                    notifications += 1
                    stop_notices += event.get('hook_event_name') == 'Stop'
                detection = event.get('loop_detection')
                if not isinstance(detection, dict):
                    continue
                policy = detection.get('policy')
                observer_errors += detection.get('status') == 'loop_observer_error'
                if isinstance(policy, dict) and type(policy.get('version')) is int:
                    versions.add(policy['version'])
                    observed += 1
                kind = {'warning': 'warnings', 'loop_detected': 'stops',
                        'loop_guard_error': 'errors', 'loop_observer_error': 'errors',
                        'excluded_slow_call': 'slow_calls'}.get(detection.get('status'))
                if not kind:
                    continue
                identity = (event.get('session_id'), event.get('agent_id'), event.get('tool_use_id'),
                            event.get('hook_event_name'), kind)
                if identity in seen:
                    continue
                seen.add(identity)
                role = detection.get('actor_role') or ('worker' if event.get('agent_id') else 'lead')
                if role not in by_role:
                    invalid += 1
                    continue
                by_role[role][kind] += 1
    measured = observed > 0 and invalid == 0 and observer_errors == 0
    return dict(measured=measured, policy_versions=sorted(versions), invalid_events=invalid,
                by_role=by_role, worker_notifications=notifications, stop_notice_emissions=stop_notices,
                triggered=any(r['warnings'] or r['stops'] for r in by_role.values()) if measured else None,
                basis='Recorded guard hooks only; missing or malformed observations are unknown, not zero')


def child_tool_evidence(profile):
    """Count retained child requests without treating tool use as semantic contribution."""
    children = {}
    root = Path(profile)
    for path in sorted(root.rglob("*.jsonl")):
        if "subagents" not in path.relative_to(root).parts or path.is_symlink():
            continue
        identity = path.stem.removeprefix("agent-")
        child = children.setdefault(identity, dict(agent_id=identity, transcript_files=[], calls={}, malformed_rows=0))
        child["transcript_files"].append(str(path.relative_to(root)))
        for index, line in enumerate(path.read_text(errors="replace").splitlines()):
            try:
                row = json.loads(line)
            except ValueError:
                child["malformed_rows"] += 1
                continue
            message = row.get("message", {}) if isinstance(row, dict) else {}
            if not isinstance(message, dict) or message.get("role") != "assistant":
                continue
            content = message.get("content", [])
            for block_index, block in enumerate(content if isinstance(content, list) else []):
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                call_id = block.get("id") or (str(path), index, block_index)
                child["calls"][call_id] = block.get("name", "unknown")
    return [dict(agent_id=child["agent_id"], transcript_files=child["transcript_files"],
                 tool_calls_observed=len(child["calls"]), tool_counts=dict(Counter(child["calls"].values())),
                 malformed_rows=child["malformed_rows"], substantive_work_status="unverified")
            for child in children.values()]


def background_shell_evidence(rows):
    handed_off = set()
    last_stop = None
    for event in rows:
        response = event.get('tool_response')
        if (event.get('tool_name') == 'Bash' and isinstance(response, dict)
                and response.get('backgroundTaskId')):
            handed_off.add(str(response['backgroundTaskId']))
        if event.get('hook_event_name') == 'Stop' and not event.get('agent_id'):
            last_stop = event
    tasks = last_stop.get('background_tasks') if last_stop is not None else None
    running = [t for t in tasks if isinstance(t, dict) and t.get('type') == 'shell'
               and t.get('status') == 'running'] if isinstance(tasks, list) else None
    return dict(bash_background_handoffs=len(handed_off),
                running_shells_at_last_stop=len(running) if running is not None else None,
                scope='Native hook observations, not completed work or post-exit process quiescence')


def timeout_waiting_evidence(folder, cutoff):
    """Read hook state at the recorded host timeout; do not infer intent from prose."""
    unknown = dict(measured=False, lead_idle_waiting=None, pending_worker_ids=None,
                   basis='Root Stop with pending workers and no subsequent lead activity before host timeout')
    path = Path(folder)/'native-profile/observer/events.jsonl'
    if not cutoff or not path.is_file():
        return unknown
    try:
        limit = datetime.fromisoformat(cutoff)
        if limit.tzinfo is None:
            return unknown
        rows = []
        for line in path.read_text().splitlines():
            event = json.loads(line)
            stamp = datetime.fromisoformat(event['observer_received_at'])
            if stamp.tzinfo is None:
                return unknown
            if stamp <= limit:
                rows.append(event)
        root = next((e.get('session_id') for e in rows if e.get('hook_event_name')=='SessionStart'), None)
        if not root:
            return unknown
        active, ended, stopped = set(), False, False
        for event in rows:
            kind = event.get('hook_event_name')
            actor = event.get('agent_id') or event.get('agentId')
            if kind=='SubagentStart' and actor:
                active.add(actor)
            elif kind=='SubagentStop' and actor:
                active.discard(actor)
            elif not actor and '/subagents/' not in str(event.get('transcript_path','')) and event.get('session_id')==root:
                if kind=='Stop':
                    stopped=True
                elif kind in {'UserPromptSubmit','PreToolUse','PostToolUse','PostToolUseFailure'}:
                    stopped=False
                elif kind=='SessionEnd':
                    ended=True
        return dict(unknown, measured=True, lead_idle_waiting=bool(stopped and active and not ended),
                    pending_worker_ids=sorted(active))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return unknown


def native_subagents(folder):
    events = Path(folder)/"native-profile/observer/events.jsonl"
    rows = [json.loads(line) for line in events.read_text().splitlines()] if events.exists() else []
    starts, stops, active = set(), set(), set()
    start_events = stop_events = 0
    root = next((r.get("session_id") for r in rows if r.get("hook_event_name") == "SessionStart"), None)
    root_end = False
    for event in rows:
        kind = event.get("hook_event_name")
        identity = event.get("agent_id") or event.get("agentId")
        if kind == "SubagentStart" and identity:
            starts.add(identity)
            active.add(identity)
            start_events += 1
        elif kind == "SubagentStop" and identity:
            stops.add(identity)
            active.discard(identity)
            stop_events += 1
        elif (kind == "SessionEnd" and event.get("session_id") == root and not identity
              and "/subagents/" not in str(event.get("transcript_path", ""))):
            root_end = True
    configs = list((Path(folder)/"native-profile/claude/teams").glob("*/config.json"))
    teammate_idle = sum(r.get("hook_event_name") == "TeammateIdle" for r in rows)
    children = child_tool_evidence(Path(folder) / "native-profile")
    # Killed native workers may have no SubagentStop hook. Reconcile counts only
    # against the same completed root session; never infer worker identity/quiescence.
    termination = None
    returned = set()
    wait_ceiling_exceeded = False
    try:
        report = json.loads((Path(folder) / "report.json").read_text())
        cli = report.get("cli", {})
        native = cli.get("native_result", {})
        stats = native.get("subagent_stats", {})
        killed = stats.get("killed", {})
        counts = [stats.get("spawned"), stats.get("completed")]
        kills = [killed.get(k) for k in ("parent", "user", "system")]
        stderr = Path(folder) / 'cli/stderr.log'
        wait_ceiling_exceeded = bool(type(killed.get('system')) is int and killed['system'] > 0
            and stderr.is_file() and re.search(
                r'^Background tasks still running after [0-9.]+s; terminating\. '
                r'Set CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0 to wait indefinitely\.$',
                stderr.read_text(errors='replace'), flags=re.MULTILINE))
        if (active and root and root_end and cli.get("status") == "cli_exited"
                and cli.get("returncode") == 0 and native.get("session_id") == root
                and native.get("terminal_reason") == "completed" and native.get("is_error") is False
                and all(type(v) is int and v >= 0 for v in counts + kills)
                and start_events == len(starts) and stop_events == len(stops)
                and stops <= starts and counts == [len(starts), len(stops)]
                and sum(kills) == len(active) and stats.get("failed") == 0):
            termination = dict(killed_by=killed, count=sum(kills), scope="aggregate_native_counts; identities_unverified")
        # A completed native Agent return can outlive a missing SubagentStop
        # (e.g. a failed worker API call). Require the same root call and identity.
        calls = {r.get('tool_use_id') for r in rows if r.get('session_id') == root
                 and r.get('hook_event_name') == 'PreToolUse' and r.get('tool_name') in {'Agent', 'Task'}
                 and not r.get('agent_id') and '/subagents/' not in str(r.get('transcript_path', ''))
                 and r.get('tool_use_id')}
        root_starts = {r.get('agent_id') for r in rows if r.get('session_id') == root
                       and r.get('hook_event_name') == 'SubagentStart'}
        for event in rows:
            response = event.get('tool_response')
            if (event.get('session_id') == root and not event.get('agent_id')
                    and '/subagents/' not in str(event.get('transcript_path', ''))
                    and event.get('hook_event_name') == 'PostToolUse'
                    and event.get('tool_name') in {'Agent', 'Task'} and event.get('tool_use_id') in calls
                    and isinstance(response, dict) and response.get('status') == 'completed'):
                identity = response.get('agentId') or response.get('agent_id')
                if identity in active & root_starts:
                    returned.add(identity)
        if not (root and root_end and cli.get('status') == 'cli_exited' and cli.get('returncode') == 0
                and native.get('session_id') == root and native.get('terminal_reason') == 'completed'
                and native.get('is_error') is False and stats.get('failed') == 0
                and start_events == len(starts) and stop_events == len(stops) and stops <= starts
                and all(type(v) is int and v >= 0 for v in counts + kills)
                and counts == [len(starts), len(stops | returned)] and sum(kills) == 0):
            returned.clear()
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    accounted = not (active - returned) or termination is not None
    complete = bool(starts) and root_end and accounted and not wait_ceiling_exceeded
    policy_rows = [r.get('mandatory_delegation') for r in rows]
    mandatory = None
    if any(isinstance(r, dict) for r in policy_rows):
        measured = all(isinstance(r, dict) and r.get('version') == 'native-delegation-v1'
                       for r in policy_rows)
        errors = sum(isinstance(r, dict) and r.get('action') == 'policy_error' for r in policy_rows)
        qualified = {r.get('agent_id') for r in rows if r.get('session_id') == root
            and r.get('hook_event_name') == 'SubagentStart'
            and isinstance(r.get('mandatory_delegation'), dict)
            and r['mandatory_delegation'].get('action') == 'worker_started'} - {None}
        mandatory = dict(version='native-delegation-v1', measured=measured,
            passed=bool(measured and qualified and not errors), worker_ids=sorted(qualified), errors=errors,
            denied_tool_calls=sum(isinstance(r, dict) and r.get('action') == 'tool_denied' for r in policy_rows),
            blocked_stops=sum(isinstance(r, dict) and r.get('action') == 'stop_blocked' for r in policy_rows))
    return dict(passed=bool(root and complete and not configs and not teammate_idle
                           and (mandatory is None or mandatory['passed'])),
                mandatory_delegation=mandatory,
                subagent_starts=start_events, subagent_stops=stop_events, unique_subagents=len(starts),
                active_subagent_ids=sorted(active),
                native_completed_return_ids=sorted(returned),
                unaccounted_subagent_ids=sorted(active - returned) if termination is None else [],
                native_team_configs=len(configs), teammate_idle_events=teammate_idle, session_end=root_end,
                structural_delegation_observed=bool(starts),
                structural_delegation_complete=complete,
                lifecycle_basis=("hooks_and_native_termination_counts" if termination else
                                 "hooks_and_native_completed_returns" if returned else "hooks"),
                native_termination_accounting=termination,
                worker_termination_accounted=accounted,
                background_wait_ceiling_exceeded=wait_ceiling_exceeded,
                workspace_quiescence="unverified",
                background_shells=background_shell_evidence(rows),
                child_tool_evidence=children,
                child_tool_evidence_status="observed_transcripts" if children else "unavailable",
                substantive_work_status="unverified",
                delegation_evidence_scope="Native lifecycle and retained tool-call requests only; no semantic contribution or result incorporation verification",
                tool_count_scope="Deduplicated retained child tool-call requests, not proof of successful execution; zero calls does not imply no useful reasoning")


def single_agent_violated(audit, accounting=None):
    fields = ('subagent_starts', 'executed_delegation_tools', 'exposed_delegation_tools',
              'member_transcript_files', 'native_team_configs', 'teammate_idle_events')
    return bool(any(audit.get(field) for field in fields) or
                (accounting or {}).get('by_role', {}).get('member', {}).get('observed_messages', 0))


def native_single_agent(folder):
    folder = Path(folder)
    events = folder/"native-profile/observer/events.jsonl"
    rows = [json.loads(line) for line in events.read_text().splitlines()] if events.exists() else []
    native = native_subagents(folder)
    tools = None
    stdout = folder/"cli/stdout.log"
    for line in stdout.open(errors="replace") if stdout.exists() else ():
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict) and value.get("type") == "system" and value.get("subtype") == "init":
            tools = value.get("tools")
    exposed = sorted(t for t in (tools or []) if claude_delegation_tool(t))
    member_files = sum("subagents" in p.relative_to(folder/"native-profile").parts
                       for p in (folder/"native-profile").rglob("*.jsonl"))
    executed = sum(r.get("hook_event_name") in {"PostToolUse", "PostToolUseFailure"}
                   and claude_delegation_tool(str(r.get("tool_name", ""))) for r in rows)
    policy = bool(rows) and all(r.get("single_agent_policy") is True for r in rows)
    start = any(r.get("hook_event_name") == "SessionStart" and r.get("session_id") for r in rows)
    passed = (start and native["session_end"] and policy and isinstance(tools, list) and not exposed
              and not native["subagent_starts"] and not executed and not member_files
              and not native["native_team_configs"] and not native["teammate_idle_events"])
    return dict(passed=bool(passed), policy_verified=policy, session_start=bool(start),
                background_shells=native['background_shells'],
                session_end=native["session_end"], subagent_starts=native["subagent_starts"],
                executed_delegation_tools=executed, exposed_delegation_tools=exposed,
                member_transcript_files=member_files, native_team_configs=native["native_team_configs"],
                teammate_idle_events=native["teammate_idle_events"],
                blocked_delegation_attempts=sum(bool(r.get("single_policy_blocked")) for r in rows))


def tool_errors(profile, backend, stdout):
    errors, calls, retry_events = {}, {}, 0
    rejections = {}
    state_writes = {}
    for path in profile.rglob("*.jsonl"):
        for line in path.read_text(errors="replace").splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            message = event.get("message") or {}
            if not isinstance(message, dict):
                continue
            for block in message.get("content", []) if isinstance(message.get("content"), list) else []:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use":
                    calls[block.get("id")] = block.get("name")
                    command = (block.get("input") or {}).get("command", "")
                    if (block.get("name") == "Bash" and isinstance(command, str)
                            and any(path in command for path in
                                    ("/native/claude/teams", "/native/claude/tasks", ".claude/teams/", ".claude/tasks/"))
                            and re.search(r"rm\s+-[rf]*[rf]|json\.dump\(|write_text\(|shutil\.rmtree\(|sed\s+-i", command)):
                        state_writes[block.get("id")] = command
                if block.get("type") == "tool_result" and block.get("is_error"):
                    errors[block.get("tool_use_id")] = "unknown"
                if block.get("type") == "tool_result":
                    content = block.get("content")
                    texts = ([content] if isinstance(content, str) else
                             [b.get("text", "") for b in content if isinstance(b, dict)]
                             if isinstance(content, list) else [])
                    for text in texts:
                        try:
                            payload = json.loads(text)
                        except (ValueError, TypeError):
                            continue
                        if isinstance(payload, dict) and payload.get("success") is False:
                            rejections[block.get("tool_use_id")] = "unknown"
    for identity in errors:
        errors[identity] = calls.get(identity, "unknown")
    for line in stdout.read_text(errors="replace").splitlines() if stdout.exists() else []:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("type") == "system" and "retry" in str(event.get("subtype", "")):
            retry_events += 1
    return dict(reported_tool_errors=len(errors), by_tool=dict(Counter(errors.values())),
                payload_rejections_by_tool=dict(Counter(calls.get(i, "unknown") for i in rejections)),
                native_state_write_commands=[dict(tool_call_id=key, command=value)
                                             for key, value in state_writes.items()],
                native_retry_events_observed=retry_events,
                scope="Explicit native error flags only; not proof that other errors or failed requests were absent")


def read_evidence(profile, backend):
    root = Path(profile).resolve()
    messages, tools, errors, files = {}, Counter(), [], []
    for path in root.rglob("*.jsonl"):
        files.append(str(path.relative_to(root)))
        scope = "member" if "subagents" in path.parts else "leader"
        with path.open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                message = event.get("message", {}) if isinstance(event, dict) else {}
                if not isinstance(message, dict) or not message.get("id") or message.get("role") != "assistant":
                    continue
                identity = message["id"]
                if identity in messages:
                    previous, previous_scope = messages[identity]
                    merged = dict(previous.get("usage", {}))
                    for key, value in message.get("usage", {}).items():
                        if isinstance(value, (int, float)):
                            merged[key] = max(merged.get(key, 0), value)
                    blocks = {json.dumps(b, sort_keys=True): b for b in
                              [*previous.get("content", []), *message.get("content", [])]}
                    message = dict(message, usage=merged, content=list(blocks.values()))
                    scope = "member" if "member" in {scope, previous_scope} else scope
                messages[identity] = (message, scope)
    tool_ids = set()
    for message, scope in messages.values():
        for block in message.get("content", []):
            if isinstance(block, dict) and block.get("type") == "tool_use":
                identity = block.get("id", json.dumps(block, sort_keys=True))
                if identity not in tool_ids:
                    tool_ids.add(identity)
                    tools[block.get("name", "unknown")] += 1
    rows = []
    for identity, (message, scope) in messages.items():
        usage = message.get("usage") or {}
        hit = usage.get("cache_read_input_tokens", 0)
        input_tokens = (usage.get("input_tokens", 0) + hit + usage.get("cache_creation_input_tokens", 0)
                        if "input_tokens" in usage else None)
        output, model = usage.get("output_tokens"), message.get("model")
        rows.append(dict(id=identity, scope=scope, model=model, input_tokens=input_tokens,
                         output_tokens=output, cache_hit_tokens=hit, native_usage=usage))
    groups = {}
    for row in rows:
        role = "leader" if row["scope"] == "leader" else "member"
        bucket = groups.setdefault(role, dict(observed_messages=0, messages_with_usage=0,
                                             input_tokens=0, output_tokens=0, cache_hit_tokens=0))
        bucket["observed_messages"] += 1
        if row["input_tokens"] is not None and row["output_tokens"] is not None:
            bucket["messages_with_usage"] += 1
            for field in ("input_tokens", "output_tokens", "cache_hit_tokens"):
                bucket[field] += row[field]
    for bucket in groups.values():
        bucket["token_weighted_cache_hit_rate"] = (bucket["cache_hit_tokens"] / bucket["input_tokens"]
                                                  if bucket["input_tokens"] else None)
    # Prices checked against the official rate card on 2026-11-02. Native CLI
    # cost estimates for Anthropic model names are not DeepSeek billing receipts.
    totals = {key: sum(b[key] for b in groups.values())
              for key in ("input_tokens", "output_tokens", "cache_hit_tokens")}
    estimated = ((totals["input_tokens"] - totals["cache_hit_tokens"]) * 0.15
                 + totals["cache_hit_tokens"] * 0.003 + totals["output_tokens"] * 0.6) / 1e6
    delegates = sum(tools.get(name, 0) for name in ("task", "Agent", "Task"))
    known = sum(b["messages_with_usage"] for b in groups.values())
    return dict(backend=backend, by_role=groups, observed_totals=totals, tools=dict(tools),
                observed_delegation_calls=delegates, native_team_create_calls=tools.get("TeamCreate", 0),
                observed_messages=rows, native_jsonl_files=files, errors=errors,
                estimated_usd_off_peak=estimated if known else None,
                estimated_usd_peak=estimated * 2 if known else None,
                accounting_coverage="Observed retained messages only; failed requests, compaction or native helper calls may be missing",
                price_source="https://api-docs.deepseek.com/quick_start/pricing/",
                child_tool_evidence=child_tool_evidence(root),
                substantive_work_status="unverified",
                team_correctness_verified=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--backend", choices=("claude-code", "claude-code-subagents", "claude-code-single-agent"), required=True)
    args = parser.parse_args()
    print(json.dumps(read_evidence(args.profile, args.backend), ensure_ascii=False, indent=2))
