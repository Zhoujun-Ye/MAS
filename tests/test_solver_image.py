import hashlib
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


@pytest.mark.parametrize('timing_contains_sentinel', [False, True])
def test_sql_probe_exports_hashes_and_denies_writes(timing_contains_sentinel):
    config = dict(external=False, timeout=1, queries=[
        'SELECT count(*) FROM events', 'DELETE FROM events', 'SELECT count(*) FROM events'])
    probe = PROBE
    if timing_contains_sentinel:
        # Reproduce the old false positive without depending on real clock digits.
        probe = ('import time\n_cpu_clock=iter([0.0, 0.120001]*3)\n'
                 'time.process_time=lambda: next(_cpu_clock)\n') + probe
    result = subprocess.run([sys.executable, '-c', probe], input=json.dumps(config),
                            text=True, capture_output=True, check=True, timeout=10)
    receipt = json.loads(result.stdout)
    assert set(receipt) == {'version', 'compile_options', 'features', 'results'}
    first, denied, last = receipt['results']
    assert first['status'] == last['status'] == 'completed'
    assert denied['status'] == 'error'
    assert denied['error_type'] == 'OperationalError'
    expected = hashlib.sha256(json.dumps([json.dumps([12000])]).encode()).hexdigest()
    assert first['ordered_sha256'] == last['ordered_sha256'] == expected
    assert first['multiset_sha256'] == last['multiset_sha256'] == expected
    assert first['rows'] == last['rows'] == 1
    completed_fields = {'query_sha256', 'status', 'rows', 'ordered_sha256', 'multiset_sha256',
                        'plan_sha256', 'scan_steps', 'automatic_index_steps', 'seconds', 'cpu_seconds'}
    assert set(first) == set(last) == completed_fields
    assert set(denied) == {'query_sha256', 'status', 'error_type', 'seconds', 'cpu_seconds'}
    for query, row in zip(config['queries'], receipt['results']):
        assert row['query_sha256'] == hashlib.sha256(query.encode()).hexdigest()
    if timing_contains_sentinel:
        assert first['cpu_seconds'] == last['cpu_seconds'] == 0.120001
        assert '12000' in result.stdout
