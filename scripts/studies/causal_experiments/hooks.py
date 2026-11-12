"""Study-only native hook wrapper; preserve baseline permission/state recording."""

import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

NULL_REPORT = '<empty_report/>'
NULL_REQUEST = 'Return exactly <empty_report/> and nothing else. Do not use tools.'
POLICY_PATH = Path('/causal/policy.json')


def brief_valid(path):
    if path.is_symlink() or not path.is_file() or not 1 <= path.stat().st_size <= 16384:
        return False
    text = path.read_text()
    sections = text.split('## ')
    found = {}
    for section in sections[1:]:
        lines = section.splitlines()
        if lines:
            found[lines[0].strip()] = '\n'.join(lines[1:]).strip()
    return all(found.get(key) for key in ('Task', 'Qualifiers', 'Sources'))


def intervention(payload, mode, work):
    event, tool = payload.get('hook_event_name'), payload.get('tool_name')
    worker = bool(payload.get('agent_id') or payload.get('agentId')
                  or '/subagents/' in str(payload.get('transcript_path', '')))
    observation = dict(version='native-causal-v1', arm=mode, action='observed')
    decision = {}
    if mode == 'null_worker':
        if event == 'PreToolUse' and not worker and tool in {'Agent', 'Task'}:
            original = dict(payload.get('tool_input') or {})
            updated = dict(description='Return an empty study report', subagent_type='general-purpose', prompt=NULL_REQUEST)
            if 'run_in_background' in original:
                updated['run_in_background'] = original['run_in_background']
            payload['tool_input'] = updated
            observation.update(action='null_worker_request', original_input=original)
            decision = dict(hookSpecificOutput=dict(hookEventName='PreToolUse',
                permissionDecision='allow', updatedInput=updated))
        elif event == 'PreToolUse' and not worker and tool == 'SendMessage':
            original = dict(payload.get('tool_input') or {})
            updated = dict(to=original.get('to'), summary='Return the empty study report', message=NULL_REQUEST)
            if 'notify_when_idle' in original:
                updated['notify_when_idle'] = original['notify_when_idle']
            payload['tool_input'] = updated
            observation.update(action='null_worker_message', original_input=original)
            decision = dict(hookSpecificOutput=dict(hookEventName='PreToolUse',
                permissionDecision='allow', updatedInput=updated))
        elif event == 'PreToolUse' and worker:
            observation['action'] = 'null_worker_tool_denied'
            decision = dict(hookSpecificOutput=dict(hookEventName='PreToolUse', permissionDecision='deny',
                permissionDecisionReason='This study worker returns an empty report and has no tools.'))
        elif event == 'SubagentStop' and worker:
            observation['empty_report_verified'] = payload.get('last_assistant_message', '').strip() == NULL_REPORT
    if mode == 'self_brief' and event == 'PreToolUse' and not worker and tool == 'Bash':
        valid = brief_valid(work/'brief.md')
        observation.update(action='brief_checked', brief_schema_valid=valid)
        if not valid:
            decision = dict(hookSpecificOutput=dict(hookEventName='PreToolUse', permissionDecision='deny',
                permissionDecisionReason='First write /workspace/brief.md using Write, with nonempty Task, Qualifiers and Sources sections.'))
            decision['hookSpecificOutput']['permissionDecisionReason']=(
                'Use Write to create /workspace/brief.md, at most 16384 UTF-8 bytes. '
                'Use literal headings ## Task, ## Qualifiers, ## Sources (no trailing colons), each with nonempty content. Then retry Bash.')
    if mode=='recon' and event=='Stop' and not worker:
        try:
            spec=importlib.util.spec_from_file_location('packet_validation',Path(__file__).with_name('packet_validation.py'))
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            module.validate_packet(work/'recon.json',Path('/data'))
            observation['packet_schema_valid']=True
        except (OSError,ValueError,TypeError,KeyError) as error:
            observation.update(packet_schema_valid=False,action='recon_stop_blocked')
            decision=dict(decision='block',reason='Fix /workspace/recon.json before finishing: '+str(error))
    payload['causal_intervention'] = observation
    return decision


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args, _ = parser.parse_known_args()
    payload = json.load(sys.stdin)
    try:
        config = json.loads(POLICY_PATH.read_text())
        if config['arm'] not in {'null_worker', 'self_brief','recon'}:
            raise ValueError('Unknown study hook policy')
        decision = intervention(payload, config['arm'], Path('/workspace'))
    except (OSError, ValueError, KeyError, TypeError) as error:
        payload['causal_intervention'] = dict(version='native-causal-v1', action='policy_error', error_type=type(error).__name__)
        decision = {'continue': False, 'stopReason': 'Study policy unavailable; stopping without retry.'}
    try:
        baseline = subprocess.run([sys.executable, '-I', '/adapter-hooks.py', *sys.argv[1:]],
            input=json.dumps(payload), capture_output=True, text=True, check=True)
        original = json.loads(baseline.stdout)
    except (OSError,ValueError,subprocess.SubprocessError):
        print(json.dumps({'continue':False,'stopReason':'Baseline policy unavailable; stopping.'}))
        return
    denied = original.get('continue') is False or original.get('hookSpecificOutput', {}).get('permissionDecision') == 'deny'
    print(json.dumps(original if denied or not decision else decision))


if __name__ == '__main__':
    main()
