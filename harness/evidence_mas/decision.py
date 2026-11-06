"""Decision protocol over executed answer observations; no model or gold access."""

import hashlib
import json
import secrets
import sqlite3
import os
import tempfile
from pathlib import Path
from decimal import Decimal

from .store import StoreError, packed, required
from .measurements import records, extract_measurements, whitespace

PROTOCOL = 'decision-v3'


def answer_key(value):
    """Compare JSON answers without rounding away distinctions or numeric structure."""
    if isinstance(value, bool) or value is None:
        return packed(value)
    if isinstance(value, (int, float)):
        number = Decimal(str(value))
        if not number.is_finite():
            raise StoreError('Nonfinite answer')
        sign, digits, exponent = number.as_tuple()
        if not any(digits):
            return 'number:0'
        while digits[-1] == 0:
            digits = digits[:-1]
            exponent += 1
        return 'number:' + packed([sign, digits, exponent])
    if isinstance(value, str):
        return 'text:' + value.strip()
    if isinstance(value, list):
        return 'list:' + packed([answer_key(x) for x in value])
    if isinstance(value, dict):
        return 'object:' + packed({k: answer_key(v) for k, v in value.items()})
    raise StoreError('Unsupported answer type')


def extract_answers(output):
    """Parse whole JSON, JSON lines or literal dictionaries; never execute text."""
    answers = []
    for item in records(output):
        if not isinstance(item, dict) or len(set(item) & {'answer','final_answer'}) != 1:
            continue
        value = item['answer'] if 'answer' in item else item['final_answer']
        if value is None or value == '':
            continue
        answer_key(value)
        answers.append(value)
    return answers


def parsed_output(store, ref):
    """Derived, versioned cache; historical read-only stores never acquire files."""
    output = store.read_blob(ref) if ref else None
    parser_hash = hashlib.sha256(Path(__file__).read_bytes() +
        Path(__file__).with_name('measurements.py').read_bytes()).hexdigest()
    key = hashlib.sha256((parser_hash + packed(output)).encode()).hexdigest()
    folder = store.root / 'parsed-output'
    path = folder / (key + '.json')
    try:
        if not folder.is_symlink() and not path.is_symlink():
            cached = json.loads(path.read_text())
            if cached['key'] == key and cached['digest'] == hashlib.sha256(packed(cached['result']).encode()).hexdigest():
                return cached['result']
    except (OSError, ValueError, KeyError, TypeError):
        pass
    diagnostics = []
    result = dict(measurements=extract_measurements(output, diagnostics=diagnostics),
                  answers=extract_answers(output), diagnostics=diagnostics)
    if not store.readonly and not folder.is_symlink():
        temporary = None
        try:
            folder.mkdir(exist_ok=True)
            fd, temporary = tempfile.mkstemp(dir=folder)
            with os.fdopen(fd, 'w') as stream:
                json.dump(dict(key=key, result=result,
                    digest=hashlib.sha256(packed(result).encode()).hexdigest()), stream)
            os.replace(temporary, path)
        except OSError:
            pass  # A disposable optimization must not become a submission dependency.
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)
    return result


class DecisionProtocol:
    def __init__(self, store):
        self.store = store

    def initialize(self, task):
        required(task, 'task')
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute("SELECT value FROM meta WHERE key='decision_task'").fetchone()
            if old and old[0] != task:
                raise StoreError('Decision task is frozen')
            db.execute('INSERT OR IGNORE INTO meta VALUES(?,?)', ('decision_task', task))
            db.execute('INSERT OR IGNORE INTO meta VALUES(?,?)', ('decision_seed', secrets.token_hex(32)))
            db.execute('INSERT OR IGNORE INTO meta VALUES(?,?)', ('decision_protocol', PROTOCOL))
            if db.execute("SELECT value FROM meta WHERE key='decision_protocol'").fetchone()[0] != PROTOCOL:
                raise StoreError('Decision protocol mismatch')

    def state(self, db):
        meta = dict(db.execute("SELECT key,value FROM meta WHERE key LIKE 'decision_%'"))
        if meta.get('decision_protocol') != PROTOCOL or 'decision_task' not in meta:
            raise StoreError('Decision protocol not initialized by launcher')
        return meta

    def snapshot(self, db):
        meta = self.state(db)
        groups = {}
        eligible, uncovered, pending, orphaned = 0, 0, 0, 0
        active = {o['identity']:o['state'] for o in self.store.latest(db, 'agent_lifecycle')}
        intermediate, invalid = [], []
        for obs in self.store.latest(db, 'observation'):
            identity = obs['agent_id'] if obs['agent_id'] != 'unknown' else obs['session_id']
            pending += obs['tool_name'] == 'Bash' and obs['status'] == 'unknown' and active.get(identity) == 'running'
            orphaned += obs['tool_name'] == 'Bash' and obs['status'] == 'unknown' and active.get(identity) != 'running'
            # Read/Write/messages merely quote data. Only completed execution is eligible.
            if obs['tool_name'] != 'Bash' or obs['status'] != 'success' or obs['completeness'] != 'complete':
                continue
            eligible += 1
            parsed = parsed_output(self.store, obs['output_ref'])
            measured = parsed['measurements']
            invalid.extend(parsed['diagnostics'])
            intermediate.extend(dict(m, observation=dict(id=obs['id'], revision=obs['revision'])) for m in measured)
            values = [(v, 'task.answer', {'quantity':'declared task answer'}) for v in parsed['answers']]
            values += [(m['value'], m['group'], m['target']) for m in measured
                       if m['confidence']=='explicit' and m['answer_target']]
            uncovered += not bool(values)
            for value, target_id, target in values:
                key = answer_key(value)
                token = hashlib.sha256((meta['decision_seed'] + key).encode()).hexdigest()[:24]
                group = groups.setdefault(token, dict(id=token, value=value, target_id='task.answer', target=target, interpretations=[], observations=[]))
                interpretation = dict(target_id=target_id, target=target)
                if interpretation not in group['interpretations']:
                    group['interpretations'].append(interpretation)
                ref = dict(id=obs['id'], revision=obs['revision'])
                if ref not in group['observations']:
                    group['observations'].append(ref)
        candidates = sorted(groups.values(), key=lambda c: c['id'])
        fingerprint = hashlib.sha256(packed([{k:c[k] for k in ('id','value','target_id')} for c in candidates]).encode()).hexdigest()
        sizes = {c['target_id']:sum(x['target_id']==c['target_id'] for x in candidates) for c in candidates}
        return dict(snapshot=fingerprint, candidates=candidates, conflict=any(n>1 for n in sizes.values()),
                    intermediate=intermediate, invalid_measurements=invalid, invalid_measurement_count=len(invalid),
                    execution_observations=eligible, uncovered_execution_observations=uncovered,
                    pending_executions=pending, orphaned_executions=orphaned)

    def view(self, cursor=0, limit=30, detail=False):
        if type(cursor) is not int or cursor < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise StoreError('Invalid pagination')
        with self.store.connect() as db:
            db.execute('BEGIN')
            state = self.snapshot(db)
            # Do not expose authors, frequency, creation order, or raw observation IDs here.
            state['candidates'] = [{k:c[k] for k in ('id','value','target_id','target','interpretations')} for c in state['candidates']]
            if not detail:
                state['intermediate'] = [m for m in state['intermediate'] if m['confidence']=='explicit']
            state['intermediate'] = [{k:m[k] for k in ('group','target','value','confidence','answer_target','variant')} for m in state['intermediate']]
            state['intermediate'] = list({packed(m):m for m in state['intermediate']}.values())
            counts = {key:len(state[key]) for key in ('candidates','intermediate')}
            for key in counts:
                state[key] = state[key][cursor:cursor+limit]
            state['counts'] = counts
            state['next_cursor'] = cursor+limit if cursor+limit < max(counts.values()) else None
            state['scope'] = 'All declared final answers compete; uncertain labels are detail-only and never submission gates'
            return state

    def read(self, candidate_id=None):
        with self.store.connect() as db:
            db.execute('BEGIN')
            if candidate_id is None:
                return dict(source='task', text=self.state(db)['decision_task'])
            state = self.snapshot(db)
            candidate = next((c for c in state['candidates'] if c['id'] == candidate_id), None)
            if candidate is None:
                raise StoreError('Unknown candidate')
            # One representative execution; duplicates do not act as votes.
            obs = self.store.ref(db, candidate['observations'][0], 'observation')
            return dict(source=candidate_id, input=packed(self.store.read_blob(obs['input_ref']))[:8000],
                        output=self.store.output_text(obs)[:8000])

    def select(self, snapshot, candidate_id, basis, comparisons, role='lead', actor='lead'):
        if role != 'lead':
            raise StoreError('Only lead can select')
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            state = self.snapshot(db)
            if snapshot != state['snapshot']:
                raise StoreError('Candidate snapshot changed; inspect again')
            selected_target = next((c['target_id'] for c in state['candidates'] if c['id']==candidate_id), None)
            ids = {c['id'] for c in state['candidates'] if c['target_id']==selected_target}
            if candidate_id not in ids:
                raise StoreError('Choice must be an executed candidate')
            task = self.state(db)['decision_task']
            if not isinstance(basis, dict) or set(basis) != {'task_quote', 'criterion'}:
                raise StoreError('Basis requires task_quote and criterion')
            required(basis['task_quote'], 'task_quote')
            required(basis['criterion'], 'criterion')
            if whitespace(basis['task_quote']) not in whitespace(task):
                raise StoreError('Task quote must be verbatim; no invented source')
            if not isinstance(comparisons, dict) or set(comparisons) != ids - {candidate_id}:
                raise StoreError('Explain each alternative under the same criterion')
            for reason in comparisons.values():
                required(reason, 'comparison')
            selection = dict(snapshot=snapshot, candidate_id=candidate_id, basis=basis,
                             comparisons=comparisons, actor=actor, semantic_validity='unverified', target_id=selected_target,
                             target_snapshot=hashlib.sha256(packed([{k:c[k] for k in ('id','value')} for c in state['candidates'] if c['target_id']==selected_target]).encode()).hexdigest())
            obj = self.store.put(db, 'decision_selection', selection, actor)
            db.execute('INSERT INTO events(body) VALUES(?)',
                       (self.store.event('decision.select', selection, obj, actor, role, None),))
            return dict(selected=candidate_id, snapshot=snapshot, semantic_validity='unverified')

    def check(self, submission, *, execution_finished=False):
        if not isinstance(submission, dict):
            raise StoreError('Submission must be a JSON object')
        fields = set(submission) & {'answer', 'final_answer'}
        if len(fields) != 1:
            raise StoreError('Expected exactly one answer field')
        value = submission[next(iter(fields))]
        if value is None or (isinstance(value, str) and not value.strip()):
            return dict(accepted=True, reason='declared_incomplete', protocol=PROTOCOL)
        with self.store.connect() as db:
            db.execute('BEGIN')
            state = self.snapshot(db)
            if state['pending_executions'] and not execution_finished:
                return dict(accepted=False, reason='execution_pending', conflict=state['conflict'])
            selections = self.store.latest(db, 'decision_selection')
            if not state['candidates']:
                return dict(accepted=True, reason='no_comparable_conflict', conflict=False,
                            coverage=bool(state['candidates']), orphaned_executions=state['orphaned_executions'], protocol=PROTOCOL)
            if state['conflict'] and not selections:
                return dict(accepted=False, reason='selection_missing', conflict=state['conflict'])
            selected = selections[-1] if selections else None
            current_target = hashlib.sha256(packed([{k:c[k] for k in ('id','value')} for c in state['candidates']]).encode()).hexdigest()
            if state['conflict'] and selected.get('target_snapshot') != current_target:
                return dict(accepted=False, reason='selection_stale', conflict=state['conflict'])
            candidate = (next((c for c in state['candidates'] if c['id'] == selected['candidate_id']), None)
                         if state['conflict'] else state['candidates'][0])
            def key(answer):
                if 'final_answer' in submission and isinstance(answer, (str,int,float)) and not isinstance(answer,bool):
                    text = str(answer).strip()
                    try:
                        parsed = json.loads(text)
                        if type(parsed) in (int,float):
                            return answer_key(parsed)
                    except ValueError:
                        pass
                    return 'text:' + text
                return answer_key(answer)
            accepted = candidate is not None and key(value) == key(candidate['value'])
            return dict(accepted=accepted, reason='consistent' if accepted else 'answer_mismatch',
                        conflict=state['conflict'], snapshot=state['snapshot'],
                        semantic_validity='unverified', protocol=PROTOCOL)


def host_check(folder, submission):
    from .store import Store
    root = folder / 'native-profile/evidence'
    if not (root / 'store.sqlite').is_file() or (root / 'degraded.jsonl').exists():
        return dict(accepted=False, reason='capture_unavailable_or_degraded')
    try:
        # Runners call only after owned-container teardown. Missing terminal hooks
        # do not imply a process still exists; live MCP calls cannot set this flag.
        return DecisionProtocol(Store(root, 'benchmark-evidence', readonly=True)).check(submission, execution_finished=True)
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
        return dict(accepted=False, reason='decision_state_invalid')


TOOLS = {
    'decision_view': dict(description='Inspect anonymous executed answer candidates and current snapshot.',
        inputSchema=dict(type='object', properties={'cursor':{'type':'integer','minimum':0},
            'limit':{'type':'integer','minimum':1,'maximum':100}, 'detail':{'type':'boolean'}}, additionalProperties=False)),
    'decision_read': dict(description='Read task text (omit candidate_id) or one candidate execution. Provenance is not proof of semantic correctness.',
        inputSchema=dict(type='object', properties={'candidate_id': {'type': 'string'}}, additionalProperties=False)),
    'decision_select': dict(description='Select from current snapshot using a whitespace-normalized task quote, criterion and reasons keyed by ALL other final-answer candidate IDs. Page through decision_view when needed. No correctness verdict is implied.',
        inputSchema=dict(type='object', properties={'snapshot': {'type':'string'}, 'candidate_id': {'type':'string'},
            'basis': {'type':'object', 'properties': {'task_quote': {'type':'string'}, 'criterion': {'type':'string'}},
                      'required':['task_quote','criterion'], 'additionalProperties':False},
            'comparisons': {'type':'object'}}, required=['snapshot','candidate_id','basis','comparisons'], additionalProperties=False)),
    'decision_check': dict(description='Check the exact submission object against the selection and current captured candidates. Does not write or submit.',
        inputSchema=dict(type='object', properties={'submission': {'type':'object'}}, required=['submission'], additionalProperties=False)),
}
