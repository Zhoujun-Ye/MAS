"""Bounded artifact export after a workspace snapshot; never executes the artifact."""

from pathlib import PurePosixPath

MAX_ARTIFACT_BYTES = 1024 * 1024


def workspace_relative_path(path, root="/workspace"):
    if not isinstance(path, str) or not path.strip() or "\x00" in path:
        raise ValueError("Expected a non-empty workspace path")
    value = PurePosixPath(path)
    if ".." in value.parts:
        raise ValueError("Parent traversal is not allowed")
    if value.is_absolute():
        try:
            value = value.relative_to(root)
        except ValueError:
            raise ValueError("Path must be inside the workspace") from None
    if not value.parts:
        raise ValueError("Expected a file or subdirectory, not the workspace root")
    return str(value)


ARTIFACT_READ_SCRIPT = r'''
import hashlib, json, os, stat, sys
args = json.load(sys.stdin)
parts = args['path'].split('/')
if not parts or any(p in ('', '.', '..') for p in parts):
    raise ValueError('Invalid relative artifact path')
directory = os.open(args['root'], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
try:
    for part in parts[:-1]:
        child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
        os.close(directory)
        directory = child
    fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    with os.fdopen(fd, 'rb') as stream:
        meta = os.fstat(stream.fileno())
        if not stat.S_ISREG(meta.st_mode) or meta.st_size > args['max_bytes']:
            raise ValueError('Artifact must be a bounded regular file')
        data = stream.read(args['max_bytes'] + 1)
    if len(data) > args['max_bytes'] or not data.strip():
        raise ValueError('Artifact is empty or exceeds the byte limit')
    digest = hashlib.sha256(data).hexdigest()
    if digest != args['sha256']:
        raise ValueError('Artifact changed after the submission snapshot')
    print(json.dumps(dict(path=args['path'], sha256=digest, bytes=len(data), content=data.decode('utf-8'))))
finally:
    os.close(directory)
'''
