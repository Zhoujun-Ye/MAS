"""Study-only native worker-role replay and controlled first-delegation continuation."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import uuid

from common.io import fingerprint
from harness import ClaudeCodeSingleAgentCLI, ClaudeCodeSubagentsCLI
from harness._claude_cli import run_print

VARIANTS = ('verbatim', 'open', 'task_only')
WORKER_REPORT = '''
For this controlled replay, return only a JSON object with these keys:
observations: a concise factual report;
checks: a list of objects with question, evidence, and conclusion strings;
candidate_answer: your supported answer to the underlying task, or null if not established.
Only claim checks you actually performed. Use the supplied /data files, not external sources.
Do not create a final pipeline or submission. Do not write files outside /tmp.
'''


def prefix(folder):
    """Cut before the first Agent result; reject unreconstructable earlier state."""
    folder = Path(folder)
    report = json.loads((folder/'report.json').read_text())
    sid = report['cli']['native_result']['session_id']
    transcript = folder/'native-profile/claude/projects/-workspace'/(sid+'.jsonl')
    rows = [json.loads(s) for s in transcript.read_text().splitlines()]
    selected = []; call = None
    for row in rows:
        if row.get('isSidechain'):
            raise ValueError('Unexpected sidechain in the lead transcript')
        message = row.get('message') or {}
        content = message.get('content')
        selected.append(row)
        calls = [b for b in content if isinstance(b,dict) and b.get('type')=='tool_use'
                 and b.get('name') in {'Agent','Task'}] if isinstance(content,list) else []
        if message.get('role')=='assistant' and calls:
            if len(calls)!=1 or any(b.get('type')=='tool_use' and b is not calls[0] for b in content):
                raise ValueError('Parallel first-delegation calls are not a portable prefix')
            call = calls[0]
            break
    if call is None:
        raise ValueError('No recorded first delegation')
    events_path = folder/'native-profile/observer/events.jsonl'
    events = [json.loads(s) for s in events_path.read_text().splitlines()]
    start = next(e for e in events if e.get('hook_event_name')=='PreToolUse'
                 and e.get('tool_use_id')==call['id'] and not e.get('agent_id'))
    before = [e for e in events if e.get('observer_received_at','') < start['observer_received_at']
              and not e.get('agent_id') and e.get('hook_event_name')=='PostToolUse']
    forbidden = {'Bash','Write','Edit','NotebookEdit','TaskCreate','TaskUpdate'}
    if any(e.get('tool_name') in forbidden for e in before):
        raise ValueError('Earlier workspace/planner mutations cannot be reconstructed from final files')
    guidance = {name:(folder/'workspace'/name).read_text() for name in ('AGENTS.md','CLAUDE.md')}
    from scripts.kramabench.cli_runtime import INSTRUCTIONS
    if any(text!=INSTRUCTIONS for text in guidance.values()):
        raise ValueError('Recorded task guidance was changed after initialization')
    return dict(session_id=sid, rows=selected, call_id=call['id'], brief=call['input']['prompt'],
        agent_type=call['input'].get('subagent_type','general-purpose'), guidance=guidance,
        provenance=dict(folder=str(folder),transcript=str(transcript),
            transcript_sha256=hashlib.sha256(transcript.read_bytes()).hexdigest(),
            events_sha256=hashlib.sha256(events_path.read_bytes()).hexdigest(),
            prefix_sha256=fingerprint(selected)),
        estimand='Immediate report delivery at the first delegation boundary; not original asynchronous arrival timing')


def edited_brief(case, variant):
    if variant == 'task_only':
        return case['question']
    text = case['prefix']['brief']
    if variant == 'open':
        for edit in case['edits']:
            if text.count(edit['before'])!=1:
                raise ValueError('Premise edit must match exactly once')
            text=text.replace(edit['before'],edit['after'],1)
    elif variant != 'verbatim':
        raise ValueError('Unknown E4 variant')
    return text


def install_prefix(profile, case, report_text):
    saved = case['prefix']
    rows = deepcopy(saved['rows'])
    last = rows[-1]
    if last.get('message',{}).get('role')!='assistant':
        raise ValueError('Prefix does not end at the assistant delegation')
    row = {k:deepcopy(v) for k,v in last.items() if k in (
        'userType','entrypoint','cwd','sessionId','version','gitBranch','timestamp')}
    row.update(type='user',uuid=str(uuid.uuid4()),parentUuid=last['uuid'],isSidechain=False,
        message=dict(role='user',content=[dict(type='tool_result',tool_use_id=saved['call_id'],
                                             content=report_text)]))
    rows.append(row)
    path = Path(profile)/'claude/projects/-workspace'/(saved['session_id']+'.jsonl')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text('\n'.join(json.dumps(r,ensure_ascii=False) for r in rows)+'\n')
    return dict(prefix_sha256=fingerprint(saved['rows']),report_sha256=fingerprint(report_text),
                installed_transcript_sha256=fingerprint(rows),path=str(path))


class ReplayAdapter:
    def __init__(self, executable, case, phase, variant, report_text=None):
        self.executable,self.case,self.phase,self.variant,self.report_text = executable,case,phase,variant,report_text

    def command(self, model, **options):
        if self.phase=='worker':
            return [*ClaudeCodeSingleAgentCLI(self.executable).command(model,**options),
                    '--agent',self.case['prefix']['agent_type']]
        return [*ClaudeCodeSubagentsCLI(self.executable).command(model,**options),
                '--resume',self.case['prefix']['session_id'],'--fork-session']

    def run(self, prompt, **kwargs):
        workspace=Path(kwargs['workspace']);profile=Path(kwargs['observer_dir']).parent
        for name,text in self.case['prefix']['guidance'].items():
            (workspace/name).write_text(text)
        if self.phase=='worker':
            actual=edited_brief(self.case,self.variant)+'\n'+WORKER_REPORT
            binding=dict(variant=self.variant,brief_sha256=fingerprint(edited_brief(self.case,self.variant)),
                         source_prefix_sha256=self.case['prefix']['provenance']['prefix_sha256'])
        else:
            if self.report_text is None:
                raise ValueError('Lead continuation needs its paired report')
            binding=install_prefix(profile,self.case,self.report_text)
            actual='Continue. This replay has 900 seconds of wall-clock time remaining.'
        result=run_print(self,actual,backend='claude-code-single-agent' if self.phase=='worker' else 'claude-code-subagents',
            single_agent=self.phase=='worker',require_delegation=False,**kwargs)
        result['e4_replay']=dict(phase=self.phase,variant=self.variant,binding=binding,
            source_prefix_policy='First delegation, no preceding successful workspace or planner mutations',
            intervention='Controlled worker-role prompt or native resumed lead tool-result replacement; not an ordinary baseline audit')
        return result


def factory(case, phase, variant, report_text=None):
    expected='claude-code-single-agent' if phase=='worker' else 'claude-code-subagents'
    def make(backend, executable):
        if backend!=expected:
            raise ValueError('Replay phase/backend mismatch')
        return ReplayAdapter(executable,case,phase,variant,report_text)
    return make
