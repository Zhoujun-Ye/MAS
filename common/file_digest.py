"""Host-only SHA256 reuse for stat-stable files; not an adversarial boundary."""

import hashlib
import json
from pathlib import Path
import sqlite3
import os
import time
from contextlib import closing


def signature(value):
    return [value.st_dev,value.st_ino,value.st_size,value.st_mtime_ns,value.st_ctime_ns]


class DigestCache:
    def __init__(self,path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)

    def digest(self,path,*,git_blob=None):
        path=Path(path)
        if path.is_symlink() or not path.is_file():raise ValueError('Expected regular input file')
        with closing(sqlite3.connect(self.path,timeout=300)) as db, db:
            table='digests' if git_blob is None else 'verified_blobs'
            db.execute(f'CREATE TABLE IF NOT EXISTS {table}(path TEXT PRIMARY KEY, signature TEXT, sha256 TEXT)')
            with path.open('rb') as stream:
                before=signature(os.fstat(stream.fileno()))
                if before!=signature(path.stat()):raise ValueError('Input replaced while opening')
                encoded=json.dumps([before,git_blob]) if git_blob is not None else json.dumps(before)
                old=db.execute(f'SELECT signature,sha256 FROM {table} WHERE path=?',(str(path.resolve()),)).fetchone()
                # Fresh writes can share coarse filesystem timestamps. Never reuse
                # a digest while that timestamp ambiguity window is still open.
                if old and old[0]==encoded and time.time_ns()-before[4]>2_000_000_000:
                    if before!=signature(path.stat()) or before!=signature(os.fstat(stream.fileno())):
                        raise ValueError('Input changed while reading cached digest')
                    return old[1]
                db.execute('BEGIN IMMEDIATE')
                old=db.execute(f'SELECT signature,sha256 FROM {table} WHERE path=?',(str(path.resolve()),)).fetchone()
                if old and old[0]==encoded and time.time_ns()-before[4]>2_000_000_000:
                    if before!=signature(path.stat()) or before!=signature(os.fstat(stream.fileno())):
                        raise ValueError('Input changed while waiting for digest cache')
                    return old[1]
                h=hashlib.sha256()
                blob=hashlib.sha1(f'blob {before[2]}\0'.encode()) if git_blob is not None else None
                for block in iter(lambda:stream.read(1024*1024),b''):
                    h.update(block)
                    if blob is not None:blob.update(block)
                if before!=signature(path.stat()) or before!=signature(os.fstat(stream.fileno())):
                    raise ValueError('Input changed while hashing')
                value=h.hexdigest()
                if blob is not None and blob.hexdigest()!=git_blob:raise ValueError('Input differs from pinned Git blob')
                db.execute(f'INSERT OR REPLACE INTO {table} VALUES(?,?,?)',(str(path.resolve()),encoded,value))
                return value
