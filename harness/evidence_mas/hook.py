"""MAS observation hook; never grants permissions or runs tools."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

from .store import Store, StoreError, packed
from .decision import DecisionProtocol, PROTOCOL


def decision_guard(store, event):
    if event.get('hook_event_name') != 'PreToolUse':
        return None
    name, args = event.get('tool_name', ''), event.get('tool_input', {})
    reason = None
    if event.get('agent_id') and name.endswith(('__decision_select', '__decision_check')):
        reason = 'Only the lead can select or validate a final decision.'
    elif name in ('Write', 'Edit') and str(args.get('file_path', '')).rstrip('/').endswith('/submission.json'):
        if name == 'Edit':
            reason = 'Validate the complete submission and use Write; partial edits cannot be checked.'
        else:
            try:
                result = DecisionProtocol(store).check(json.loads(args.get('content', '')))
                if not result['accepted']:
                    reason = 'Decision gate: ' + result['reason'] + '. Use decision_view/select/check.'
            except (ValueError, OSError, KeyError):
                reason = 'Decision state or submission is unavailable; final write cannot be validated.'
    if reason:
        return dict(hookSpecificOutput=dict(hookEventName='PreToolUse', permissionDecision='deny',
                                           permissionDecisionReason=reason))
    return None


def collect(store, event):
    kind = event.get('hook_event_name')
    if kind in ('SessionStart', 'SessionEnd', 'SubagentStart', 'SubagentStop'):
        identity = event.get('agent_id') or event.get('session_id')
        if identity:
            if kind in ('SubagentStart', 'SubagentStop') and event.get('agent_id'):
                with store.connect() as db:
                    db.execute('CREATE TABLE IF NOT EXISTS native_workers(identity TEXT PRIMARY KEY, state TEXT)')
                    db.execute('INSERT OR REPLACE INTO native_workers VALUES(?,?)',
                               (identity, 'running' if kind=='SubagentStart' else 'stopped'))
            return store.call('agent.lifecycle', dict(identity=identity,
                state='running' if kind.endswith('Start') else 'stopped'), role='collector')
        return None
    if kind not in ('PreToolUse', 'PostToolUse', 'PostToolUseFailure'):
        return None
    name = event.get('tool_name', 'unknown')
    if name.startswith(('mcp__evidence__', 'mcp__evidence_worker__')):
        # Store.call already audits these accesses; do not recursively capture reads.
        return None
    status = {'PreToolUse': 'unknown', 'PostToolUse': 'success', 'PostToolUseFailure': 'failed'}[kind]
    output = event.get('tool_response') if kind == 'PostToolUse' else event.get('error')
    if event.get('is_interrupt') or (isinstance(output, dict) and output.get('interrupted')):
        status = 'cancelled'
    has_overflow = name == 'Bash' and isinstance(output, dict) and any(
        key in output for key in ('persistedOutputPath', 'persistedOutputSize'))
    truncated = event.get('truncated') or (isinstance(output, dict) and output.get('truncated'))
    args = dict(tool_name=name, tool_input=event.get('tool_input', {}), tool_output=output,
                session_id=event.get('session_id') or 'unknown',
                agent_id=event.get('agent_id') or 'unknown',
                tool_call_id=event.get('tool_use_id') or 'unknown', status=status,
                completeness='missing' if output is None else 'truncated' if truncated else
                             'pointer' if has_overflow else 'complete')
    # Only deduplicate where the native runtime supplied a call identity.
    key = hashlib.sha256(packed([kind, args]).encode()).hexdigest() if args['tool_call_id'] != 'unknown' else None
    observation = store.call('obs.capture', args, actor=args['agent_id'], role='collector', operation_id=key)
    if (name == 'TaskStop' and status == 'success' and isinstance(output, dict)
            and output.get('task_type') == 'local_agent' and not output.get('is_error')
            and output.get('task_id') == event.get('tool_input', {}).get('task_id')
            and output.get('task_id')):
        store.call('agent.lifecycle', dict(identity=output['task_id'], state='stopped'), role='collector')
    return observation


def response(event, observation):
    if event.get('hook_event_name') == 'PreToolUse' and event.get('agent_id'):
        args = event.get('tool_input', {})
        name = event.get('tool_name', '')
        # Interface guard, not shell sandboxing: aliases and same-UID writes require host audit.
        if (name in ('Write', 'Edit', 'MultiEdit', 'Bash') and
                'submission.json' in packed(args)):
            return dict(hookSpecificOutput=dict(hookEventName='PreToolUse', permissionDecision='deny',
                permissionDecisionReason='Final submission belongs to the lead; workers return intermediate results only.'))
    return {}


def wait_guard(store, event):
    """Reject only explicit agent-placeholder waits after observed worker shutdown."""
    from .sharing import pure_delay
    import re
    if event.get('hook_event_name') != 'PreToolUse' or event.get('agent_id'):
        return None
    if not pure_delay(dict(event, hook_event_name='PostToolUse')):
        return None
    description = event.get('tool_input', {}).get('description', '')
    if not isinstance(description, str) or not re.search(r'\b(?:subagent|agent|worker)s?\b', description, re.I):
        return None
    with store.connect() as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='native_workers'").fetchone():
            return None
        states = [row[0] for row in db.execute('SELECT state FROM native_workers')]
        if not states or any(state!='stopped' for state in states):
            return None
        if any(o['tool_name'] in ('Agent','Task') and o['status']=='unknown'
               for o in store.latest(db,'observation')):
            return None
        reason = ('All observed native workers have stopped. Do not sleep to wait for their reports; '
                  'inspect delivered native results or shared observations. This does not prove correctness.')
        db.execute('INSERT INTO events(body) VALUES(?)',
                   (store.event('workspace.wait_blocked', {}, {'reason':'observed_workers_stopped'},
                                'lead','lead',None),))
    return dict(hookSpecificOutput=dict(hookEventName='PreToolUse', permissionDecision='deny',
                                       permissionDecisionReason=reason))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--protocol', choices=('observations-v1', PROTOCOL), default='observations-v1')
    parser.add_argument('--share-context', action='store_true')
    parser.add_argument('--mode', choices=('full', 'observations'), default='observations')
    args = parser.parse_args()
    reply = {}
    try:
        event = json.load(sys.stdin)
        if not isinstance(event,dict):
            raise StoreError('Native event must be an object',code='invalid_native_event')
        # A permission guard must not depend on storage availability.
        reply = response(event, None)
        if reply:
            print(json.dumps(reply))
            return
        store = Store(args.root, args.run_id)
        if args.share_context:
            guard = wait_guard(store, event)
            if guard:
                print(json.dumps(guard))
                return
        if args.protocol == PROTOCOL:
            guard = decision_guard(store, event)
            if guard:
                print(json.dumps(guard))
                return
        observation = collect(store, event)
        reply = response(event, observation)
        if args.share_context and not reply:
            from .sharing import context_reply
            reply = context_reply(store, event, args.mode)
    except Exception as exc:
        # Never leak payloads, paths, or secrets through a hook error message.
        print('Evidence collection degraded: ' + type(exc).__name__, file=sys.stderr)
        try:
            if any(p.is_symlink() for p in (args.root.absolute(), *args.root.absolute().parents)):
                raise OSError('Unsafe degradation marker path')
            args.root.mkdir(parents=True, exist_ok=True)
            marker = args.root / 'degraded.jsonl'
            if not marker.is_symlink():
                import os
                fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, 'a') as stream:
                    metadata=dict(status='degraded',error_type=type(exc).__name__,error_code=getattr(exc,'code','hook_error'))
                    if isinstance(locals().get('event'),dict):
                        metadata.update(hook_event=event.get('hook_event_name') if isinstance(event.get('hook_event_name'),str) else 'unknown',
                                        tool_name=event.get('tool_name') if isinstance(event.get('tool_name'),str) else 'unknown')
                        try:
                            metadata['event_sha256']=hashlib.sha256(packed(event).encode()).hexdigest()
                        except (TypeError,ValueError):
                            pass
                    stream.write(packed(metadata) + '\n')
        except (OSError,TypeError,ValueError):
            pass
    print(json.dumps(reply))


if __name__ == '__main__':
    main()
