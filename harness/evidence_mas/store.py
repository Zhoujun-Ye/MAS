"""Shared Evidence Workspace: run-bound observations and execution evidence."""

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
                CREATE INDEX IF NOT EXISTS object_kind_revision ON objects(kind, id, revision);
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
                          '(SELECT id, MAX(revision) r FROM objects ' +
                          ('WHERE kind=? ' if kind is not None else '') +
                          'GROUP BY id) x ON o.id=x.id AND o.revision=x.r ORDER BY o.rowid',
                          (kind,) if kind is not None else ()).fetchall()
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
            'obs.capture': self.capture,
            'obs.list': self.obs_list, 'obs.search': self.obs_search, 'obs.read': self.obs_read,
            'workspace.trace': self.trace,
        }
        if method not in methods or not isinstance(arguments, dict):
            raise StoreError('Unknown method or invalid arguments')
        fingerprint = hashlib.sha256(packed([method, arguments, actor, role]).encode()).hexdigest()
        if operation_id is not None:
            identifier(operation_id)
            operation_key = hashlib.sha256(packed([role, actor, operation_id]).encode()).hexdigest()
        readonly = method in {'obs.list', 'obs.search', 'obs.read', 'workspace.trace'}
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
                if old:
                    if old[0] != fingerprint:
                        raise StoreError('Idempotency key reused for different request')
                    return json.loads(old[1])
            try:
                result = methods[method](db, actor, role, **arguments)
            except TypeError as exc:
                raise StoreError('Invalid method arguments') from exc
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


    def capture(self, db, actor, role, tool_name, tool_input, tool_output=None,
                session_id='unknown', agent_id='unknown', tool_call_id='unknown',
                status='unknown', completeness='missing'):
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
        output_ref = self.blob(tool_output) if tool_output is not None else None
        body = dict(tool_name=tool_name,
            input_ref=self.blob(tool_input), output_ref=output_ref, output_hash=output_ref,
            terminal_input_ref=self.blob(tool_input) if status!='unknown' or completeness!='missing' else None,
            input_transform=None,
            session_id=session_id, agent_id=agent_id, tool_call_id=tool_call_id,
            status=status, completeness=completeness)
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
        edges = []
        for obj in objects:
            references = []
            for field in ('observation',):
                if obj.get(field):
                    references.append((field, obj[field]))
            for field in ('observations',):
                references += [(field, r) for r in obj.get(field, [])]
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
