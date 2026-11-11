"""Read recorded retired-workspace artifacts without reviving its runtime."""

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import sqlite3


class WorkspaceReader:
    def __init__(self, root, run_id='benchmark-evidence'):
        self.root = Path(root).absolute()
        if any(p.is_symlink() for p in (self.root, *self.root.parents)):
            raise ValueError('Historical workspace must not contain symlinks')
        self.database = self.root / 'store.sqlite'
        if self.database.is_symlink() or not self.database.is_file():
            raise ValueError('Missing regular historical store')
        wal = self.root / 'store.sqlite-wal'
        if wal.exists() and wal.stat().st_size:
            raise ValueError('Historical store has an uncheckpointed WAL; do not modify it during analysis')
        with self.connect() as db:
            row = db.execute("SELECT value FROM meta WHERE key='run_id'").fetchone()
            if not row or row[0] != run_id:
                raise ValueError('Historical store belongs to another run')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database.as_uri() + '?mode=ro&immutable=1', uri=True)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA query_only=ON')
            yield db
        finally:
            db.close()

    def latest(self, db, kind):
        rows = db.execute('SELECT o.body FROM objects o JOIN '
            '(SELECT id, MAX(revision) r FROM objects WHERE kind=? GROUP BY id) x '
            'ON o.id=x.id AND o.revision=x.r ORDER BY o.rowid', (kind,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def read_blob(self, reference):
        if not isinstance(reference, str) or not re.fullmatch('[0-9a-f]{64}', reference):
            raise ValueError('Invalid historical blob reference')
        path = self.root / 'blobs' / reference
        if path.parent.is_symlink() or path.is_symlink():
            raise ValueError('Historical blob must not be a symlink')
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != reference:
            raise ValueError('Historical blob integrity mismatch')
        return json.loads(data)

    def recorded_state(self, events):
        views = [self.read_blob(e['result_ref']) for e in events if e['method']=='decision.view']
        if not views:
            return dict(available=False, candidates=[], intermediate=[], candidate_count=None,
                        conflict=None, complete=False, invalid_measurement_count=None)
        last = views[-1]
        if last.get('protocol') not in {'decision-v3', 'decision-v4'}:
            raise ValueError('Unsupported historical decision-view protocol')
        pages = [v for v in views if v.get('snapshot')==last['snapshot']]
        candidates = {c['id']:c for v in pages for c in v.get('candidates',[])}
        intermediate = {json.dumps(m,sort_keys=True):m for v in pages for m in v.get('intermediate',[])}
        count = last.get('counts',{}).get('candidates')
        return dict(available=True, candidates=list(candidates.values()), intermediate=list(intermediate.values()),
                    candidate_count=count, complete=count is not None and count==len(candidates),
                    conflict=last.get('conflict'), invalid_measurement_count=last.get('invalid_measurement_count'))
