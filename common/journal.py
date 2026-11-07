"""Durable phase claims: an uncertain external side effect is never replayed."""

from contextlib import contextmanager
import fcntl
import json
from pathlib import Path
import sqlite3


@contextmanager
def exclusive(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Run or phase is still owned by another process') from None
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


class Journal:
    def __init__(self, path):
        self.path = Path(path)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS phases('
                       'phase TEXT, identity TEXT, binding TEXT, state TEXT, body TEXT, '
                       'PRIMARY KEY(phase,identity))')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.execute('PRAGMA synchronous=FULL')
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, phase, identity):
        with self.connect() as db:
            row = db.execute('SELECT binding,state,body FROM phases WHERE phase=? AND identity=?',
                             (phase,json.dumps(identity))).fetchone()
        return dict(binding=row[0],state=row[1],body=json.loads(row[2])) if row else None

    def claim(self, phase, identity, binding, body):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT INTO phases VALUES(?,?,?,?,?)',
                       (phase,json.dumps(identity),binding,'claimed',json.dumps(body)))

    def finish(self, phase, identity, binding, body):
        with self.connect() as db:
            result = db.execute('UPDATE phases SET state=?,body=? WHERE phase=? AND identity=? AND binding=?',
                               ('complete',json.dumps(body),phase,json.dumps(identity),binding))
            if result.rowcount != 1:
                raise ValueError('Missing phase claim or changed artifact binding')
