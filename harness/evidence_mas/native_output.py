"""Snapshot native overflow files as evidence, never as reconstructed stdout."""

import os
from pathlib import Path
import stat


MAX_BYTES = 4 * 1024 * 1024


def persisted_output(store, output):
    if not isinstance(output, dict) or not any(
            key in output for key in ('persistedOutputPath', 'persistedOutputSize')):
        return None, None
    name, size = output.get('persistedOutputPath'), output.get('persistedOutputSize')
    if not isinstance(name, str) or type(size) is not int or size < 0:
        return None, 'invalid_pointer'
    path = Path(name)
    base = store.root.parent / 'claude' / 'projects'
    if (not path.is_absolute() or '..' in path.parts or not path.is_relative_to(base)
            or path.parent.name != 'tool-results' or path.suffix != '.txt'
            or any(p.is_symlink() for p in (path, *path.parents))):
        return None, 'unsafe_path'
    if size > MAX_BYTES:
        return None, 'too_large'
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                return None, 'not_regular'
            if before.st_size != size:
                return None, 'size_mismatch'
            data = stream.read(MAX_BYTES + 1)
            after = os.fstat(stream.fileno())
        fingerprint = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if len(data) != size or fingerprint(before) != fingerprint(after):
            return None, 'changed_during_read'
        return data.decode('utf-8'), 'captured'
    except UnicodeError:
        return None, 'invalid_utf8'
    except (OSError, ValueError):
        return None, 'unavailable'
