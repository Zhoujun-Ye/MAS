import json
import subprocess
import sys

import pytest

from scripts.server.prepare_solver_image import sqlite_flags, sqlite_sources
from scripts.probes.sqlite_runtime import PROBE


def test_sqlite_compile_options_are_preserved_not_shell_input():
    assert sqlite_flags(['COMPILER=gcc-12', 'MUTEX_PTHREADS', 'SYSTEM_MALLOC',
                         'THREADSAFE=1', 'ENABLE_FTS5', 'DEFAULT_CACHE_SIZE=-2000']) == [
        '-DSQLITE_THREADSAFE=1', '-DSQLITE_ENABLE_FTS5', '-DSQLITE_DEFAULT_CACHE_SIZE=-2000']
    with pytest.raises(ValueError):
        sqlite_flags(['ENABLE_FTS5;false'])
    assert sqlite_flags(['MAX_MMAP_SIZE=0x7fff0000']) == ['-DSQLITE_MAX_MMAP_SIZE=0x7fff0000']


def test_sqlite_archive_rejected_before_extraction(tmp_path):
    archive = tmp_path / 'untrusted.tar.gz'
    archive.write_bytes(b'not the pinned release')
    with pytest.raises(ValueError, match='official release hash'):
        sqlite_sources(archive)


def test_sql_probe_exports_hashes_and_denies_writes():
    config = dict(external=False, timeout=1, queries=[
        'SELECT count(*) FROM events', 'DELETE FROM events', 'SELECT count(*) FROM events'])
    result = subprocess.run([sys.executable, '-c', PROBE], input=json.dumps(config),
                            text=True, capture_output=True, check=True, timeout=10)
    receipt = json.loads(result.stdout)
    first, denied, last = receipt['results']
    assert first['status'] == last['status'] == 'completed'
    assert denied['status'] == 'error'
    assert first['ordered_sha256'] == last['ordered_sha256']
    assert first['rows'] == 1
    assert '12000' not in result.stdout
