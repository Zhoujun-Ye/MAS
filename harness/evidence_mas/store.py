"""Shared Evidence Workspace: observations, claims, evidence and decisions."""

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from datetime import datetime, timezone
import uuid


class StoreError(ValueError):
    def __init__(self, message, *, code='store_error'):
        super().__init__(message)
        self.code = code


def send_message_alias_pruning(before, after):
    """Claude 2.1.286 retains canonical inputs but removes compatibility fields."""
    canonical = {'to', 'summary', 'message'}
    aliases = {'type', 'recipient', 'content'}
    return (isinstance(before, dict) and isinstance(after, dict)
            and set(after) == canonical and canonical < set(before) <= canonical | aliases
            and all(before[key] == after[key] for key in canonical))


def packed(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def required(value, name):
    if not isinstance(value, str) or not value.strip():
        raise StoreError(f'{name} must be nonempty text')
    return value


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value):
        raise StoreError('Invalid identifier')
    return value


class Store:
    def __init__(self, root, run_id, *, readonly=False):
        self.readonly = readonly
        self.run_id = identifier(run_id)
        self.root = Path(root).absolute()
        if any(p.is_symlink() for p in (self.root, *self.root.parents)):
            raise StoreError('Store path must not contain symlinks')
        self.blobs = self.root / 'blobs'
        if self.blobs.is_symlink() or (self.root / 'store.sqlite').is_symlink():
            raise StoreError('Symlink storage is not supported')
        if readonly:
            with self.connect() as db:
                bound = db.execute("SELECT value FROM meta WHERE key='run_id'").fetchone()
                if not bound or bound[0] != run_id:
                    raise StoreError('Store belongs to another run')
            return
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.blobs.mkdir(exist_ok=True, mode=0o700)
        with self.connect() as db:
            ready = db.execute("SELECT 1 FROM sqlite_master WHERE name='observation_identity'").fetchone()
            if ready:
                bound = db.execute("SELECT value FROM meta WHERE key='run_id'").fetchone()
                if bound and bound[0] != run_id:
                    raise StoreError('Store belongs to another run')
                if bound:
                    return
            db.executescript('''
                CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
                CREATE TABLE IF NOT EXISTS objects(
                    id TEXT, revision INTEGER, kind TEXT, body TEXT,
                    PRIMARY KEY(id, revision));
                CREATE TABLE IF NOT EXISTS operations(
                    id TEXT PRIMARY KEY, fingerprint TEXT, result TEXT);
                CREATE TABLE IF NOT EXISTS events(
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, body TEXT);
                CREATE INDEX IF NOT EXISTS observation_identity ON objects(
                    json_extract(body, '$.session_id'), json_extract(body, '$.agent_id'),
                    json_extract(body, '$.tool_call_id'), revision DESC)
                    WHERE kind='observation';
            ''')
            db.execute('INSERT OR IGNORE INTO meta VALUES(?,?)', ('run_id', run_id))
            if db.execute("SELECT value FROM meta WHERE key='run_id'").fetchone()[0] != run_id:
                raise StoreError('Store belongs to another run')
        os.chmod(self.root / 'store.sqlite', 0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect((self.root / 'store.sqlite').as_uri() + '?mode=ro', uri=True, timeout=15) if self.readonly else sqlite3.connect(self.root / 'store.sqlite', timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def blob(self, value):
        if self.readonly:
            raise StoreError('Read-only store')
        data = packed(value).encode('utf-8')
        digest = hashlib.sha256(data).hexdigest()
        target = self.blobs / digest
        if target.is_symlink():
            raise StoreError('Symlink blob')
        if not target.exists():
            fd, name = tempfile.mkstemp(dir=self.blobs)
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(name, target)
            finally:
                if os.path.exists(name):
                    os.unlink(name)
        return digest

    def read_blob(self, digest):
        if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
            raise StoreError('Invalid blob hash')
        path = self.blobs / digest
        if path.is_symlink():
            raise StoreError('Symlink blob')
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise StoreError('Blob integrity mismatch')
        return json.loads(data)

    def get(self, db, object_id, revision=None, kind=None):
        identifier(object_id)
        if revision is not None and (type(revision) is not int or revision < 1):
            raise StoreError('Invalid revision')
        row = db.execute('SELECT body FROM objects WHERE id=? ' +
                         ('AND revision=? ' if revision is not None else '') +
                         'ORDER BY revision DESC LIMIT 1',
                         (object_id, revision) if revision is not None else (object_id,)).fetchone()
        if not row:
            raise StoreError('Unknown object or revision')
        obj = json.loads(row[0])
        if kind and obj['kind'] != kind:
            raise StoreError('Wrong reference kind')
        return obj

    def latest(self, db, kind=None):
        rows = db.execute('SELECT o.body FROM objects o JOIN '
                          '(SELECT id, MAX(revision) r FROM objects GROUP BY id) x '
                          'ON o.id=x.id AND o.revision=x.r ORDER BY o.rowid').fetchall()
        values = [json.loads(r[0]) for r in rows]
        return [v for v in values if kind is None or v['kind'] == kind]

    def put(self, db, kind, body, actor, object_id=None, expected=None):
        if object_id:
            old = self.get(db, object_id, kind=kind)
            if type(expected) is not int or expected != old['revision']:
                raise StoreError('Revision conflict')
            revision = expected + 1
        else:
            object_id, revision = uuid.uuid4().hex, 1
        obj = dict(body, id=object_id, revision=revision, kind=kind,
                   run_id=self.run_id, actor=actor,
                   timestamp=datetime.now(timezone.utc).isoformat())
        db.execute('INSERT INTO objects VALUES(?,?,?,?)',
                   (object_id, revision, kind, packed(obj)))
        return obj

    def call(self, method, arguments, actor='unknown', role='worker', operation_id=None):
        required(actor, 'actor')
        if role not in ('lead', 'worker', 'collector'):
            raise StoreError('Invalid role')
        methods = {
            'agent.lifecycle': self.lifecycle,
            'source.register': self.source, 'execution.register': self.execution,
            'outcome.register': self.outcome, 'obs.capture': self.capture,
            'artifact.read': self.artifact_read,
            'obs.list': self.obs_list, 'obs.search': self.obs_search, 'obs.read': self.obs_read,
            'ledger.open_issue': self.issue, 'ledger.propose': self.propose,
            'ledger.revise_candidate': self.revise, 'ledger.attach': self.attach,
            'ledger.record_selection': self.select, 'ledger.view': self.view,
            'ledger.history': self.history,
            'workspace.trace': self.trace, 'ledger.retract_evidence': self.retract_evidence,
        }
        if method not in methods or not isinstance(arguments, dict):
            raise StoreError('Unknown method or invalid arguments')
        fingerprint = hashlib.sha256(packed([method, arguments, actor, role]).encode()).hexdigest()
        if operation_id is not None:
            identifier(operation_id)
            operation_key = hashlib.sha256(packed([role, actor, operation_id]).encode()).hexdigest()
        readonly = method in {'artifact.read', 'obs.list', 'obs.search', 'obs.read',
                              'ledger.view', 'ledger.history', 'workspace.trace'}
        if self.readonly and not readonly:
            raise StoreError('Read-only store')
        # Read a consistent snapshot without holding the writer reservation during blob I/O.
        if readonly and (operation_id is None or self.readonly):
            with self.connect() as db:
                db.execute('BEGIN')
                try:
                    result = methods[method](db, actor, role, **arguments)
                except TypeError as exc:
                    raise StoreError('Invalid method arguments') from exc
            if self.readonly:
                return result
            event = self.event(method, arguments, result, actor, role, operation_id)
            with self.connect() as db:
                db.execute('INSERT INTO events(body) VALUES(?)', (event,))
            return result
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if operation_id is not None:
                old = db.execute('SELECT fingerprint,result FROM operations WHERE id=?', (operation_key,)).fetchone()
                # Retain exact historical retries, without inheriting another actor's key.
                if not old:
                    legacy = db.execute('SELECT fingerprint,result FROM operations WHERE id=?', (operation_id,)).fetchone()
                    old = legacy if legacy and legacy[0] == fingerprint else None
                if old:
                    if old[0] != fingerprint:
                        raise StoreError('Idempotency key reused for different request')
                    return json.loads(old[1])
            try:
                result = methods[method](db, actor, role, **arguments)
            except TypeError as exc:
                raise StoreError('Invalid method arguments') from exc
            if method in {'ledger.propose', 'ledger.revise_candidate', 'ledger.record_selection'}:
                self.check_cycles(db)
            db.execute('INSERT INTO events(body) VALUES(?)',
                       (self.event(method, arguments, result, actor, role, operation_id),))
            if operation_id is not None:
                db.execute('INSERT INTO operations VALUES(?,?,?)', (operation_key, fingerprint, packed(result)))
            return result

    def event(self, method, arguments, result, actor, role, operation_id):
        return packed(dict(method=method, actor=actor, role=role, operation_id=operation_id,
                           arguments_ref=self.blob(arguments), result_ref=self.blob(result),
                           timestamp=datetime.now(timezone.utc).isoformat()))

    def lifecycle(self, db, actor, role, identity, state):
        if role != 'collector' or state not in ('running', 'stopped'):
            raise StoreError('Invalid lifecycle event')
        required(identity, 'identity')
        return self.put(db, 'agent_lifecycle', dict(identity=identity, state=state), actor)

    def ref(self, db, ref, kind=None):
        if not isinstance(ref, dict) or set(ref) != {'id', 'revision'}:
            raise StoreError('Reference requires id and revision')
        return self.get(db, ref['id'], ref['revision'], kind)

    def source(self, db, actor, role, source_type, content):
        if source_type not in ('task', 'codebook', 'document', 'data_manifest'):
            raise StoreError('Invalid source type')
        required(content, 'content')
        return self.put(db, 'source', dict(source_type=source_type, content_ref=self.blob(content)), actor)

    def artifact_read(self, db, actor, role, ref, start=0, end=None):
        obj = self.ref(db, ref)
        field = {'source': 'content_ref', 'execution': 'code_ref', 'outcome': 'result_ref'}.get(obj['kind'])
        if field is None:
            raise StoreError('Not a readable artifact')
        value = self.read_blob(obj[field])
        text = value if isinstance(value, str) else packed(value)
        end = min(len(text), start+8000) if end is None and type(start) is int else end
        self.span(text, start, end)
        if end-start > 16000:
            raise StoreError('Read span exceeds 16000 characters')
        return dict(artifact=obj, text=text[start:end], start=start, end=end, total=len(text))

    def execution(self, db, actor, role, code, parameters, inputs):
        required(code, 'code')
        if not isinstance(parameters, dict) or not isinstance(inputs, list) or not inputs:
            raise StoreError('Execution requires parameters and versioned inputs')
        for ref in inputs:
            self.ref(db, ref, 'source')
        return self.put(db, 'execution', dict(code_ref=self.blob(code), parameters=parameters, inputs=inputs), actor)

    def outcome(self, db, actor, role, execution_ref, obs_id, result, status):
        self.ref(db, execution_ref, 'execution')
        obs = self.get(db, obs_id, kind='observation')
        if status not in ('success', 'failed', 'cancelled', 'unknown') or status != obs['status']:
            raise StoreError('Outcome status must match observation')
        return self.put(db, 'outcome', dict(execution_ref=execution_ref, obs_id=obs_id,
                        result_ref=self.blob(result), status=status), actor)

    def capture(self, db, actor, role, tool_name, tool_input, tool_output=None,
                session_id='unknown', agent_id='unknown', tool_call_id='unknown',
                status='unknown', completeness='missing', artifact_refs=None):
        if role != 'collector':
            raise StoreError('Only collector may capture observations')
        for name, value in [('tool_name', tool_name), ('session_id', session_id),
                            ('agent_id', agent_id), ('tool_call_id', tool_call_id)]:
            required(value, name)
        if status not in ('success', 'failed', 'cancelled', 'unknown'):
            raise StoreError('Invalid observation status')
        if completeness not in ('complete', 'truncated', 'pointer', 'missing'):
            raise StoreError('Invalid completeness')
        if tool_output is None and completeness != 'missing':
            raise StoreError('Missing output cannot be complete')
        if artifact_refs is not None and not isinstance(artifact_refs, list):
            raise StoreError('artifact_refs must be a list')
        for ref in artifact_refs or []:
            self.ref(db, ref)
        output_ref = self.blob(tool_output) if tool_output is not None else None
        body = dict(tool_name=tool_name,
            input_ref=self.blob(tool_input), output_ref=output_ref, output_hash=output_ref,
            terminal_input_ref=self.blob(tool_input) if status!='unknown' or completeness!='missing' else None,
            input_transform=None,
            session_id=session_id, agent_id=agent_id, tool_call_id=tool_call_id,
            status=status, completeness=completeness, artifact_refs=artifact_refs or [])
        row = db.execute("SELECT body FROM objects WHERE kind='observation' "
                         "AND json_extract(body, '$.session_id')=? "
                         "AND json_extract(body, '$.agent_id')=? "
                         "AND json_extract(body, '$.tool_call_id')=? ORDER BY revision DESC LIMIT 1",
                         (session_id, agent_id, tool_call_id)).fetchone() if tool_call_id != 'unknown' else None
        prior = json.loads(row[0]) if row else None
        if prior:
            if prior['tool_name'] != tool_name:
                raise StoreError('Conflicting tool call identity',code='tool_call_identity_conflict')
            if prior['input_ref'] != body['input_ref']:
                previous_input=self.read_blob(prior['input_ref'])
                is_start=status=='unknown' and completeness=='missing'
                if tool_name=='SendMessage' and not is_start and send_message_alias_pruning(previous_input,tool_input):
                    body['input_ref']=prior['input_ref']
                    body['input_transform']='native_send_message_alias_pruning'
                elif (tool_name=='SendMessage' and is_start and (prior['output_ref'] is not None or prior['status']!='unknown')
                      and send_message_alias_pruning(tool_input,previous_input)):
                    # Parallel hooks can commit the terminal event before its start.
                    merged={k:v for k,v in prior.items() if k not in ('id','revision','kind','run_id','actor','timestamp')}
                    merged.update(input_ref=body['input_ref'],terminal_input_ref=prior['input_ref'],
                                  input_transform='native_send_message_alias_pruning')
                    return self.put(db,'observation',merged,actor,prior['id'],prior['revision'])
                else:
                    raise StoreError('Conflicting tool call identity',code='tool_call_identity_conflict')
            if status == 'unknown' and completeness == 'missing':
                return prior
            if prior['output_ref'] is not None or prior['status']!='unknown':
                if all(prior[k] == v for k, v in body.items()):
                    return prior
                raise StoreError('Conflicting terminal tool result',code='terminal_result_conflict')
        return self.put(db, 'observation', body, actor,
                        prior['id'] if prior else None, prior['revision'] if prior else None)

    def obs_list(self, db, actor, role, filters=None, cursor=0, limit=50):
        filters = {} if filters is None else filters
        if not isinstance(filters, dict) or set(filters) - {'agent_id', 'session_id', 'tool_name', 'tool_call_id', 'status'}:
            raise StoreError('Invalid observation filters')
        if type(cursor) is not int or cursor < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise StoreError('Invalid pagination')
        rows = [o for o in self.latest(db, 'observation') if all(o[k] == v for k, v in filters.items())]
        return dict(items=[self.observation_summary(o) for o in rows[cursor:cursor+limit]],
                    next_cursor=cursor+limit if cursor+limit < len(rows) else None)

    def obs_search(self, db, actor, role, query, filters=None, cursor=0, limit=50):
        required(query, 'query')
        # Search scans private blobs, returns metadata only; callers request bounded spans.
        self.obs_list(db, actor, role, filters, cursor, limit)
        rows = [o for o in self.latest(db, 'observation')
                if all(o[k] == v for k, v in (filters or {}).items())
                and query.casefold() in (packed(self.read_blob(o['input_ref'])) + '\n' + self.output_text(o)).casefold()]
        return dict(items=[self.observation_summary(o) for o in rows[cursor:cursor+limit]],
                    next_cursor=cursor+limit if cursor+limit < len(rows) else None)

    def observation_summary(self, obs):
        return dict({k: obs[k] for k in ('id', 'revision', 'agent_id', 'tool_name', 'status', 'completeness')},
                    input_summary=packed(self.read_blob(obs['input_ref']))[:240],
                    preview=self.output_text(obs)[:240])

    def output_text(self, obs):
        value = self.read_blob(obs['output_ref']) if obs['output_ref'] else ''
        return value if isinstance(value, str) else packed(value)

    def obs_read(self, db, actor, role, obs_id, start=0, end=None, field='output'):
        obs = self.get(db, obs_id, kind='observation')
        if field not in ('input', 'output'):
            raise StoreError('Observation field must be input or output')
        value = self.output_text(obs) if field == 'output' else packed(self.read_blob(obs['input_ref']))
        if type(start) is not int or start < 0 or (end is not None and (type(end) is not int or end < start)):
            raise StoreError('Invalid character span')
        end = min(len(value), start + (8000 if end is None else 16000), len(value) if end is None else end)
        start = min(start, len(value))
        return dict(observation=obs, text=value[start:end], start=start, end=end, total=len(value))

    @staticmethod
    def span(value, start, end):
        if type(start) is not int or type(end) is not int or not 0 <= start <= end <= len(value):
            raise StoreError('Invalid character span')

    def issue(self, db, actor, role, question, source_refs, analysis_scope):
        required(question, 'question')
        required(analysis_scope, 'analysis_scope')
        if not isinstance(source_refs, list):
            raise StoreError('source_refs must be a list')
        for ref in source_refs:
            self.ref(db, ref, 'source')
        return self.put(db, 'issue', dict(question=question, source_refs=source_refs,
                        analysis_scope=analysis_scope), actor)

    def candidate_fields(self, db, body):
        required(body['alternative'], 'alternative')
        if body['disposition'] not in ('active', 'withdrawn'):
            raise StoreError('Invalid candidate disposition')
        if not isinstance(body['assumptions'], list) or not all(isinstance(x, str) for x in body['assumptions']):
            raise StoreError('assumptions must be a list of text')
        if type(body['dependencies_complete']) is not bool or not isinstance(body['depends_on'], list):
            raise StoreError('Invalid dependency declaration')
        for ref in body['depends_on']:
            dep = self.ref(db, ref)
            if dep['kind'] not in ('candidate', 'selection'):
                raise StoreError('Dependencies must reference candidate or selection')
        if body['execution_ref']:
            self.ref(db, body['execution_ref'], 'execution')
        if body['outcome_ref']:
            outcome = self.ref(db, body['outcome_ref'], 'outcome')
            if outcome['execution_ref'] != body['execution_ref']:
                raise StoreError('Outcome and execution versions do not match')

    def propose(self, db, actor, role, issue_id, alternative, assumptions,
                execution_ref=None, outcome_ref=None, depends_on=None, dependencies_complete=False):
        self.get(db, issue_id, kind='issue')
        body = dict(issue_id=issue_id, alternative=alternative, assumptions=assumptions,
                    execution_ref=execution_ref, outcome_ref=outcome_ref,
                    depends_on=[] if depends_on is None else depends_on, dependencies_complete=dependencies_complete,
                    disposition='active')
        self.candidate_fields(db, body)
        obj = self.put(db, 'candidate', body, actor)
        return self.decorate(db, obj)

    def revise(self, db, actor, role, candidate_id, expected_revision, changes, rationale,
               confirmation_evidence_ids=None):
        required(rationale, 'rationale')
        old = self.get(db, candidate_id, kind='candidate')
        fields = {'alternative', 'assumptions', 'execution_ref', 'outcome_ref', 'depends_on', 'dependencies_complete', 'disposition'}
        if not isinstance(changes, dict) or set(changes) - fields:
            raise StoreError('Invalid candidate changes')
        body = {k: old.get(k, 'active') if k == 'disposition' else old[k] for k in fields | {'issue_id'}}
        body.update(changes)
        self.candidate_fields(db, body)
        evidence = [] if confirmation_evidence_ids is None else confirmation_evidence_ids
        if not isinstance(evidence, list):
            raise StoreError('confirmation_evidence_ids must be a list')
        for eid in evidence:
            link = self.get(db, eid, kind='evidence')
            if link.get('disposition') == 'retracted':
                raise StoreError('Retracted evidence cannot confirm applicability')
            if link['target_id'] not in (candidate_id, old['issue_id']):
                raise StoreError('Confirmation evidence targets another issue')
        reusing = old['outcome_ref'] is not None and body['outcome_ref'] == old['outcome_ref']
        if reusing and body['disposition'] != 'withdrawn' and (body['execution_ref'] != old['execution_ref'] or not evidence):
            raise StoreError('Reusing an outcome requires unchanged execution and applicability evidence')
        body.update(rationale=rationale, confirmation_evidence_ids=evidence)
        obj = self.put(db, 'candidate', body, actor, candidate_id, expected_revision)
        return self.decorate(db, obj)

    def attach(self, db, actor, role, target_id, relation, claim, scope, limitation,
               obs_id=None, source_ref=None, start=0, end=None):
        target = self.get(db, target_id)
        if target['kind'] not in ('issue', 'candidate') or relation not in ('supports', 'contradicts', 'contextual'):
            raise StoreError('Invalid evidence target or relation')
        required(claim, 'claim')
        required(scope, 'scope')
        required(limitation, 'limitation')
        if (obs_id is None) == (source_ref is None):
            raise StoreError('Evidence requires exactly one observation or source')
        if obs_id:
            value = self.output_text(self.get(db, obs_id, kind='observation'))
        else:
            value = self.read_blob(self.ref(db, source_ref, 'source')['content_ref'])
        end = len(value) if end is None else end
        self.span(value, start, end)
        if start == end:
            raise StoreError('Evidence span must be nonempty')
        return self.put(db, 'evidence', dict(target_id=target_id, target_revision=target['revision'],
            relation=relation, claim=claim, scope=scope, limitation=limitation,
            obs_id=obs_id, source_ref=source_ref, start=start, end=end, disposition='active'), actor)

    def retract_evidence(self, db, actor, role, evidence_id, expected_revision, rationale):
        required(rationale, 'rationale')
        old = self.get(db, evidence_id, kind='evidence')
        if actor != old['actor'] and role != 'lead':
            raise StoreError('Only author or lead may retract evidence')
        body = {k: v for k, v in old.items() if k not in ('id', 'revision', 'kind', 'run_id', 'actor', 'timestamp')}
        body.update(disposition='retracted', retraction_rationale=rationale)
        return self.put(db, 'evidence', body, actor, evidence_id, expected_revision)

    def select(self, db, actor, role, issue_id, choice, rationale, considered_ids,
               evidence_refs, expected_revision, disclose_unconfirmed=False):
        if role != 'lead':
            raise StoreError('Only lead may record selection (interface policy, not authentication)')
        self.get(db, issue_id, kind='issue')
        required(rationale, 'rationale')
        if type(expected_revision) is not int or expected_revision < 0 or type(disclose_unconfirmed) is not bool:
            raise StoreError('Invalid selection revision or disclosure')
        if not isinstance(considered_ids, list) or not isinstance(evidence_refs, list):
            raise StoreError('Selection references must be lists')
        for cid in considered_ids:
            if self.get(db, cid, kind='candidate')['issue_id'] != issue_id:
                raise StoreError('Candidate belongs to another issue')
        if choice is not None:
            candidate = self.ref(db, choice, 'candidate')
            if candidate.get('disposition') == 'withdrawn':
                raise StoreError('Withdrawn candidates cannot be selected')
            if candidate['issue_id'] != issue_id or choice['id'] not in considered_ids:
                raise StoreError('Choice must be a considered candidate of this issue')
            if self.decorate(db, candidate)['freshness'] != 'current' and disclose_unconfirmed is not True:
                raise StoreError('Must disclose stale/unknown choice')
        for ref in evidence_refs:
            evidence = self.ref(db, ref, 'evidence')
            current = self.get(db, ref['id'], kind='evidence')
            if current['revision'] != ref['revision'] or current.get('disposition') == 'retracted':
                raise StoreError('Selection evidence must be current and active')
            if evidence['target_id'] not in [issue_id, *considered_ids]:
                raise StoreError('Unrelated selection evidence')
        old = next((x for x in self.latest(db, 'selection') if x['issue_id'] == issue_id), None)
        if not old and expected_revision != 0:
            raise StoreError('Initial selection expects revision zero')
        return self.put(db, 'selection', dict(issue_id=issue_id, choice=choice,
            rationale=rationale, considered_ids=considered_ids, evidence_refs=evidence_refs,
            disclose_unconfirmed=disclose_unconfirmed,
            evidence_watermark=max((r[0] for r in db.execute('SELECT rowid FROM objects WHERE kind=?', ('evidence',))), default=0)),
            actor, old['id'] if old else None, expected_revision if old else None)

    def decorate(self, db, candidate, stack=None):
        stack = set() if stack is None else set(stack)
        key = (candidate['id'], candidate['revision'])
        if key in stack:
            raise StoreError('Cyclic dependency')
        stack.add(key)
        reasons = []
        if candidate.get('disposition') == 'withdrawn':
            reasons.append(dict(reason='candidate_withdrawn', id=candidate['id']))
        unknown = not candidate['dependencies_complete']
        if self.get(db, candidate['id'])['revision'] != candidate['revision']:
            reasons.append(dict(reason='candidate_superseded', id=candidate['id']))
        for ref in candidate['depends_on']:
            dep = self.ref(db, ref)
            latest = self.get(db, dep['id'])
            if latest['revision'] != ref['revision']:
                reasons.append(dict(reason='dependency_superseded', old=ref,
                                    new=dict(id=latest['id'], revision=latest['revision'])))
            if dep['kind'] == 'selection':
                if dep['choice'] is None:
                    unknown = True
                    continue
                dep = self.ref(db, dep['choice'], 'candidate')
            state = self.decorate(db, dep, stack)
            if state['freshness'] == 'stale':
                reasons.append(dict(reason='upstream_stale', dependency=ref, causes=state['stale_reasons']))
            unknown |= state['freshness'] == 'unknown'
        linked = any(e.get('disposition', 'active') == 'active' and
                     (e['target_id'] == candidate['issue_id'] or
                      (e['target_id'] == candidate['id'] and e['target_revision'] == candidate['revision']))
                     for e in self.latest(db, 'evidence'))
        return dict(candidate, freshness='stale' if reasons else 'unknown' if unknown else 'current',
                    stale_reasons=reasons, claim_status='evidence_linked' if linked else 'hypothesis')

    def check_cycles(self, db):
        candidates = {x['id']: x for x in self.latest(db, 'candidate')}
        edges = {}
        for cid, obj in candidates.items():
            edges[cid] = []
            for ref in obj['depends_on']:
                dep = self.get(db, ref['id'])
                if dep['kind'] == 'selection':
                    if dep['issue_id'] == obj['issue_id']:
                        raise StoreError('Candidate cannot depend on its own issue selection')
                    dep = self.ref(db, dep['choice']) if dep['choice'] else None
                if dep:
                    edges[cid].append(dep['id'])
        done = set()
        def visit(cid, active):
            if cid in active:
                raise StoreError('Cyclic dependency')
            if cid in done:
                return
            for child in edges.get(cid, []):
                visit(child, active | {cid})
            done.add(cid)
        for cid in edges:
            visit(cid, set())

    def view(self, db, actor, role, issue_id, since_revision=None, detail=False):
        if type(detail) is not bool:
            raise StoreError('detail must be boolean')
        issue = self.get(db, issue_id, kind='issue')
        candidates = [self.decorate(db, c) for c in self.latest(db, 'candidate') if c['issue_id'] == issue_id]
        ids = {issue_id, *(c['id'] for c in candidates)}
        evidence = [e for e in self.latest(db, 'evidence') if e['target_id'] in ids]
        selection = next((s for s in self.latest(db, 'selection') if s['issue_id'] == issue_id), None)
        needs_review = False
        if selection:
            if selection['choice']:
                selected = self.decorate(db, self.ref(db, selection['choice'], 'candidate'))
                needs_review = selected['freshness'] != 'current'
            new_evidence = db.execute('SELECT body FROM objects WHERE kind=? AND rowid>?',
                                     ('evidence', selection['evidence_watermark'])).fetchall()
            needs_review |= any(json.loads(row[0])['target_id'] in ids for row in new_evidence)
        if not detail:
            def brief(obj, fields):
                return {k: obj[k] for k in ('id', 'revision', *fields) if k in obj}
            issue = brief(issue, ('question',))
            candidates = [brief(c, ('alternative', 'actor', 'freshness', 'claim_status', 'disposition')) for c in candidates]
            evidence = [brief(e, ('target_id', 'relation', 'obs_id', 'source_ref', 'disposition')) for e in evidence]
            selection = brief(selection, ('choice', 'disclose_unconfirmed')) if selection else None
        return dict(issue=issue, candidates=candidates, evidence=evidence, selection=selection,
                    status='open' if not selection else 'resolved' if selection['choice'] else 'unresolved',
                    needs_review=needs_review, since_revision=since_revision,
                    view_mode='full_snapshot' if detail else 'summary')

    def history(self, db, actor, role, object_id, cursor=0, limit=50):
        self.get(db, object_id)
        if type(cursor) is not int or cursor < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise StoreError('Invalid pagination')
        rows = db.execute('SELECT body FROM objects WHERE id=? ORDER BY revision LIMIT ? OFFSET ?',
                          (object_id, limit+1, cursor)).fetchall()
        return dict(items=[json.loads(r[0]) for r in rows[:limit]],
                    next_cursor=cursor+limit if len(rows) > limit else None)

    def bind_mode(self, mode):
        if mode not in ('full', 'observations'):
            raise StoreError('Unknown workspace mode')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT OR IGNORE INTO meta VALUES(?,?)', ('mode', mode))
            if db.execute("SELECT value FROM meta WHERE key='mode'").fetchone()[0] != mode:
                raise StoreError('Workspace mode is frozen for this run')

    def trace(self, db, actor, role, object_id, revision=None, direction='both', max_nodes=100):
        """Trace typed/versioned references in both directions without loading payloads."""
        start = self.get(db, object_id, revision)
        if direction not in ('both', 'outbound', 'inbound') or type(max_nodes) is not int or not 1 <= max_nodes <= 200:
            raise StoreError('Invalid graph query')
        objects = [json.loads(r[0]) for r in db.execute('SELECT body FROM objects ORDER BY rowid')]
        by_key = {(o['id'], o['revision']): o for o in objects}
        latest = {o['id']: o for o in objects}
        edges = []
        for obj in objects:
            references = []
            for field in ('execution_ref', 'outcome_ref', 'source_ref', 'choice'):
                if obj.get(field):
                    references.append((field, obj[field]))
            for field in ('depends_on', 'inputs', 'source_refs', 'evidence_refs', 'artifact_refs'):
                references += [(field, r) for r in obj.get(field, [])]
            for field in ('issue_id', 'obs_id', 'target_id'):
                if obj.get(field):
                    target = latest[obj[field]]
                    references.append((field, dict(id=target['id'], revision=obj.get('target_revision', target['revision']) if field == 'target_id' else target['revision'])))
            for relation, target in references:
                edges.append(dict(source=dict(id=obj['id'], revision=obj['revision']), target=target, relation=relation))
        def key(ref):
            return ref['id'], ref['revision']
        seen, queue, selected_edges = {key(start)}, [key(start)], []
        truncated = False
        while queue:
            current = queue.pop(0)
            for edge in edges:
                a, b = key(edge['source']), key(edge['target'])
                other = b if a == current and direction in ('both', 'outbound') else a if b == current and direction in ('both', 'inbound') else None
                if other is None:
                    continue
                if other not in seen:
                    if len(seen) >= max_nodes:
                        truncated = True
                        continue
                    seen.add(other)
                    queue.append(other)
                if edge not in selected_edges:
                    selected_edges.append(edge)
        return dict(nodes=[by_key[k] for k in sorted(seen)], edges=selected_edges, truncated=truncated,
                    history_included=True, payloads_included=False)
