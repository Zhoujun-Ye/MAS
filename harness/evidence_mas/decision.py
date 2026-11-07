"""Decision protocol over executed answer observations; no model or gold access."""

import hashlib
import json
import secrets
import sqlite3
import os
import tempfile
from functools import lru_cache
from pathlib import Path
from decimal import Decimal

from .store import StoreError, packed, required
from .measurements import records, extract_measurements, whitespace

PROTOCOL = 'decision-v4'
READABLE_PROTOCOLS = ('decision-v3', PROTOCOL)


def complete_access(rows):
    """Union paginated reads of one execution, without counting overlap twice."""
    for field in ('input', 'output'):
        end = 0
        total = rows[0]['total'][field]
        for row in sorted(rows, key=lambda r: r['start']):
            if row['start'] > end:
                break
            end = max(end, row['start'] + row[field + '_characters'])
        if end < total:
            return False
    return True


def review_token(candidate):
    return hashlib.sha256(packed({k:candidate[k] for k in
        ('id','value','target_id','interpretations')}).encode()).hexdigest()


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


@lru_cache(maxsize=1)
def parser_version():
    return hashlib.sha256(Path(__file__).read_bytes() +
        Path(__file__).with_name('measurements.py').read_bytes()).hexdigest()


def parsed_output(store, ref):
    """Derived, versioned cache; historical read-only stores never acquire files."""
    output = store.read_blob(ref) if ref else None
    key = hashlib.sha256((parser_version() + packed(ref)).encode()).hexdigest()
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
        if meta.get('decision_protocol') not in READABLE_PROTOCOLS or 'decision_task' not in meta:
            raise StoreError('Decision protocol not initialized by launcher')
        if meta['decision_protocol']!=PROTOCOL and not self.store.readonly:
            raise StoreError('Retained protocol is read-only; launch a fresh current-protocol store')
        return meta

    def snapshot(self, db):
        meta = self.state(db)
        legacy = meta['decision_protocol'] == 'decision-v3'
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
            values = [(v, 'task.answer', {'quantity':'declared task answer'}, {}) for v in parsed['answers']]
            values += [(m['value'], m['group'], m['target'], m['variant']) for m in measured
                       if m['confidence']=='explicit' and m['answer_target']]
            uncovered += not bool(values)
            for value, target_id, target, variant in values:
                key = answer_key(value)
                token = hashlib.sha256((meta['decision_seed'] + key).encode()).hexdigest()[:24]
                group = groups.setdefault(token, dict(id=token, value=value, target_id='task.answer', target=target, interpretations=[], observations=[]))
                interpretation = dict(target_id=target_id, target=target)
                if not legacy:
                    interpretation['variant'] = variant
                if interpretation not in group['interpretations']:
                    group['interpretations'].append(interpretation)
                ref = dict(id=obs['id'], revision=obs['revision'])
                if ref not in group['observations']:
                    group['observations'].append(ref)
        candidates = sorted(groups.values(), key=lambda c: c['id'])
        fields = ('id','value','target_id') if legacy else ('id','value','target_id','interpretations')
        if not legacy:
            for candidate in candidates:
                candidate['interpretations'].sort(key=packed)
        fingerprint = hashlib.sha256(packed([{k:c[k] for k in fields} for c in candidates]).encode()).hexdigest()
        sizes = {c['target_id']:sum(x['target_id']==c['target_id'] for x in candidates) for c in candidates}
        return dict(snapshot=fingerprint, protocol=meta['decision_protocol'], candidates=candidates, conflict=any(n>1 for n in sizes.values()),
                    intermediate=intermediate, invalid_measurements=invalid, invalid_measurement_count=len(invalid),
                    execution_observations=eligible, uncovered_execution_observations=uncovered,
                    pending_executions=pending, orphaned_executions=orphaned)

    def access_status(self, db, state, actor):
        receipts = self.store.latest(db, 'decision_access')
        result = {}
        for candidate in state['candidates']:
            token = review_token(candidate)
            sources = {}
            refs = {packed(ref) for ref in candidate['observations']}
            for receipt in receipts:
                ref = packed(receipt['observation'])
                if (receipt['actor']==actor and receipt.get('review_token')==token
                        and 'total' in receipt and ref in refs):
                    sources.setdefault(ref, []).append(receipt)
            complete = any(complete_access(pages) for pages in sources.values())
            # Prefer the newest declared execution when a changed interpretation needs review.
            source_cursor = len(candidate['observations'])-1
            start = 0
            for index, ref in enumerate(candidate['observations']):
                pages = sources.get(packed(ref))
                if not pages:
                    continue
                source_cursor = index
                ends = []
                for field in ('input','output'):
                    end = 0
                    for page in sorted(pages, key=lambda r:r['start']):
                        if page['start']>end:
                            break
                        end = max(end,page['start']+page[field+'_characters'])
                    if end<pages[0]['total'][field]:
                        ends.append(end)
                start = min(ends) if ends else 0
                break
            result[candidate['id']] = dict(complete=complete, review_token=token,
                next_read=None if complete else dict(candidate_id=candidate['id'],
                    source_cursor=source_cursor,start=start))
        return result

    def view(self, cursor=0, limit=30, detail=False, actor='lead', role='lead'):
        if type(cursor) is not int or cursor < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise StoreError('Invalid pagination')
        with self.store.connect() as db:
            db.execute('BEGIN')
            state = self.snapshot(db)
            access = self.access_status(db, state, actor) if role=='lead' else {}
            # Do not expose authors, frequency, creation order, or raw observation IDs here.
            state['candidates'] = [{k:c[k] for k in ('id','value','target_id','target','interpretations')} for c in state['candidates']]
            for candidate in state['candidates']:
                if candidate['id'] in access:
                    candidate['evidence_access'] = access[candidate['id']]
            shapes = {type(c['value']).__name__ for c in state['candidates']}
            state['representation_warning'] = ('Mixed answer representations: compare the declared output contracts; '
                'analysis dictionaries are not automatically equivalent to a scalar answer. No candidate was discarded.'
                if len(shapes)>1 and shapes & {'dict','list'} else None)
            if not detail:
                state['intermediate'] = [m for m in state['intermediate'] if m['confidence']=='explicit']
            state['intermediate'] = [{k:m[k] for k in ('group','target','value','confidence','answer_target','variant')} for m in state['intermediate']]
            state['intermediate'] = list({packed(m):m for m in state['intermediate']}.values())
            groups = {}
            for m in state['intermediate']:
                if m['confidence'] != 'explicit':
                    continue
                group = groups.setdefault(m['group'],dict(id=m['group'],target=m['target'],results=[]))
                item = {k:m[k] for k in ('value','variant','answer_target')}
                if item not in group['results']:
                    group['results'].append(item)
            state['contrasts'] = [dict(g, differing_values=len({answer_key(r['value']) for r in g['results']})>1)
                                  for g in groups.values() if len(g['results'])>1]
            counts = {key:len(state[key]) for key in ('candidates','intermediate','contrasts')}
            for key in counts:
                state[key] = state[key][cursor:cursor+limit]
            state['counts'] = counts
            state['next_cursor'] = cursor+limit if cursor+limit < max(counts.values()) else None
            state['review_required'] = state['conflict'] and state['protocol']==PROTOCOL
            state['scope'] = 'All declared final answers compete; explicit intermediate contrasts are review leads, not automatic final candidates. Uncertain labels never gate submission.'
            return state

    def read(self, candidate_id=None, group_id=None, start=0, limit=8000, source_cursor=0, actor='lead', role='lead'):
        if (type(start) is not int or start<0 or type(limit) is not int or not 1<=limit<=16000
                or type(source_cursor) is not int or source_cursor<0 or (candidate_id and group_id)):
            raise StoreError('Invalid evidence read range or selector')
        with self.store.connect() as db:
            db.execute('BEGIN' if self.store.readonly else 'BEGIN IMMEDIATE')
            if candidate_id is None and group_id is None:
                return dict(source='task', text=self.state(db)['decision_task'])
            state = self.snapshot(db)
            if candidate_id:
                candidate = next((c for c in state['candidates'] if c['id'] == candidate_id), None)
                if candidate is None:
                    raise StoreError('Unknown candidate')
                refs = candidate['observations']
            else:
                refs = [m['observation'] for m in state['intermediate']
                        if m['group']==group_id and m['confidence']=='explicit']
                refs = list({packed(ref):ref for ref in refs}.values())
                if not refs:
                    raise StoreError('Unknown explicit intermediate group')
            if source_cursor >= len(refs):
                raise StoreError('Unknown evidence source cursor')
            obs = self.store.ref(db, refs[source_cursor], 'observation')
            text = dict(input=packed(self.store.read_blob(obs['input_ref'])), output=self.store.output_text(obs))
            result = dict(source=candidate_id or group_id, snapshot=state['snapshot'], observation=refs[source_cursor],
                **{key:value[start:start+limit] for key,value in text.items()}, start=start,
                total={key:len(value) for key,value in text.items()},
                next_start=start+limit if any(len(v)>start+limit for v in text.values()) else None,
                next_source_cursor=source_cursor+1 if source_cursor+1<len(refs) else None,
                scope='Bounded execution evidence access, not proof of correctness or independent reasoning')
            if not self.store.readonly and role=='lead' and candidate_id:
                self.store.put(db, 'decision_access',dict(candidate_id=candidate_id, snapshot=state['snapshot'],
                    review_token=review_token(candidate),
                    observation=refs[source_cursor], input_characters=len(result['input']),
                    output_characters=len(result['output']), start=start, total=result['total']), actor)
                result['evidence_access'] = self.access_status(db,state,actor)[candidate_id]
            return result

    def select(self, snapshot, candidate_id, basis, comparisons, role='lead', actor='lead'):
        if role != 'lead':
            raise StoreError('Only lead can select')
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            state = self.snapshot(db)
            if snapshot != state['snapshot']:
                raise StoreError('Candidate snapshot changed; call decision_view for the current snapshot and '
                                 'per-candidate next_read. Unchanged candidate reads remain valid.')
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
            if state['protocol']==PROTOCOL:
                access = self.access_status(db,state,actor)
                missing = [access[key]['next_read'] for key in sorted(ids) if not access[key]['complete']]
                if missing:
                    raise StoreError('Candidate evidence unread. Required decision_read arguments: ' + packed(missing) +
                                     '. Follow next_start for text pages. next_source_cursor alone is optional; '
                                     'one complete execution per current candidate is sufficient.')
            selection = dict(snapshot=snapshot, candidate_id=candidate_id, basis=basis,
                             comparisons=comparisons, actor=actor, semantic_validity='unverified', target_id=selected_target,
                             review_snapshot=snapshot,
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
                            coverage=False, semantic_validity='unverified',
                            orphaned_executions=state['orphaned_executions'], protocol=state['protocol'])
            if state['conflict'] and not selections:
                return dict(accepted=False, reason='selection_missing', conflict=state['conflict'])
            selected = selections[-1] if selections else None
            current_target = hashlib.sha256(packed([{k:c[k] for k in ('id','value')} for c in state['candidates']]).encode()).hexdigest()
            if state['conflict'] and selected.get('target_snapshot') != current_target:
                return dict(accepted=False, reason='selection_stale', conflict=state['conflict'])
            if state['conflict'] and state['protocol']==PROTOCOL and selected.get('review_snapshot')!=state['snapshot']:
                return dict(accepted=False, reason='selection_stale', conflict=True)
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
                        conflict=state['conflict'], snapshot=state['snapshot'], coverage=True,
                        semantic_validity='unverified', protocol=state['protocol'],
                        target_contract_explicit=any(len(i['target'])==6 for i in candidate['interpretations']) if candidate else False)


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
    'decision_read': dict(description='Read task text (omit selectors), candidate execution or explicit intermediate group. Use start/limit for text pages and source_cursor for further executions. Lead must access each conflicting candidate before selection; access is not comprehension.',
        inputSchema=dict(type='object', properties={'candidate_id': {'type': 'string'}, 'group_id': {'type':'string'},
            'start':{'type':'integer','minimum':0}, 'limit':{'type':'integer','minimum':1,'maximum':16000},
            'source_cursor':{'type':'integer','minimum':0}}, additionalProperties=False)),
    'decision_select': dict(description='Select from current snapshot using a whitespace-normalized task quote, criterion and reasons keyed by ALL other final-answer candidate IDs. Page through decision_view when needed. No correctness verdict is implied.',
        inputSchema=dict(type='object', properties={'snapshot': {'type':'string'}, 'candidate_id': {'type':'string'},
            'basis': {'type':'object', 'properties': {'task_quote': {'type':'string'}, 'criterion': {'type':'string'}},
                      'required':['task_quote','criterion'], 'additionalProperties':False},
            'comparisons': {'type':'object'}}, required=['snapshot','candidate_id','basis','comparisons'], additionalProperties=False)),
    'decision_check': dict(description='Check the exact submission object against the selection and current captured candidates. Does not write or submit.',
        inputSchema=dict(type='object', properties={'submission': {'type':'object'}}, required=['submission'], additionalProperties=False)),
}
