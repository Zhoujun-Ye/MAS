"""Read-only model/tool interval unions, separate from CPU time and CLI cleanup."""

from collections import Counter
from datetime import datetime
import json
import re


def timestamp(value):
    return datetime.fromisoformat(value).timestamp()


def merged(intervals):
    result = []
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if result and start <= result[-1][1]:
            result[-1] = (result[-1][0], max(end, result[-1][1]))
        else:
            result.append((start, end))
    return result


def duration(intervals):
    return sum(b-a for a, b in merged(intervals))


def timing(folder, report):
    start, end = timestamp(report['started_at']), timestamp(report['finished_at'])
    wall = end-start
    clip = lambda values: [(max(start,a), min(end,b)) for a,b in values if min(end,b)>max(start,a)]
    records = [json.loads(line) for line in (folder/'gateway-requests.jsonl').read_text().splitlines()]
    model = clip([(timestamp(r['dispatched_at']), timestamp(r['finished_at'])) for r in records
        if r.get('event') in {'finished','shutdown'} and r.get('route')=='/anthropic/v1/messages'
        and r.get('upstream_attempted') and r.get('dispatched_at') and r.get('finished_at')])
    events = [json.loads(line) for line in (folder/'native-profile/observer/events.jsonl').read_text().splitlines()]
    starts, bash, tool_counts, mcp_errors, sleep_commands = {}, [], Counter(), 0, 0
    for event in events:
        name, kind = event.get('tool_name'), event.get('hook_event_name')
        if kind=='PreToolUse':
            tool_counts[name] += 1
            if name=='Bash' and re.search(r'\bsleep\s',event.get('tool_input',{}).get('command','')):
                sleep_commands += 1
        if name and name.startswith('mcp__evidence') and kind in {'PostToolUse','PostToolUseFailure'}:
            response = event.get('tool_response')
            mcp_errors += kind=='PostToolUseFailure' or (isinstance(response,dict) and response.get('isError') is True)
        if name!='Bash' or not event.get('tool_use_id'):
            continue
        key = (event.get('session_id'), event.get('agent_id'), event['tool_use_id'])
        if kind=='PreToolUse':
            starts.setdefault(key, timestamp(event['observer_received_at']))
        elif kind in {'PostToolUse','PostToolUseFailure'} and key in starts:
            bash.append((starts.pop(key), timestamp(event['observer_received_at'])))
    bash = clip(bash)
    m, b, both = duration(model), duration(bash), duration(model+bash)
    return dict(cli_window_seconds=wall, model_inflight_union_seconds=m, bash_union_seconds=b,
        overlap_seconds=m+b-both, neither_seconds=max(0, wall-both), unmatched_bash_starts=len(starts),
        native_tool_counts=dict(tool_counts), sleep_commands=sleep_commands, detected_mcp_errors=mcp_errors,
        window_scope='Attempt timestamps include teardown; native CLI/process/cleanup times are recorded separately'), start
