"""Explicit implementation-only patches, using a disposable Git index."""
from pathlib import PurePosixPath
import re
import shlex


def checked(workspace, command, *, exact=False):
    result = workspace.execute(command)
    if result['exit_code'] or result['truncated']:
        raise RuntimeError('Snapshot command failed or output truncated')
    return result['output'] if exact else result['output'].strip()


def implementation_path(path):
    p = PurePosixPath(path)
    if (not path or p.is_absolute() or '..' in p.parts or str(p) != path
            or any(c in path for c in '\n\r\x00')):
        return False
    if any(part.lower() in {'.git', '.cooperbench_scratch', 'tests', 'test', '__tests__', 'testdata', '__pycache__'}
           for part in p.parts):
        return False
    return not (re.search(r'(^test_|_test\.|\.test\.|\.spec\.|^repro(?:duce)?[_.]|^scratch[_.]|^debug[_.])', p.name)
                or p.suffix in {'.log', '.tmp', '.pyc'})


def capture(workspace, base, paths=None):
    if not re.fullmatch(r'[0-9a-f]{40,64}', base):
        raise ValueError('Expected a pinned base commit')
    changed = checked(workspace, f'git diff --name-only -z {base}', exact=True).split('\0')
    untracked = checked(workspace, 'git ls-files --others --exclude-standard -z', exact=True).split('\0')
    candidates = set(changed + untracked) - {''}
    eligible = {p for p in candidates if implementation_path(p)}
    if paths is None:
        # Terminal capture is diagnostic, not an implicit successful submission.
        selected = sorted(eligible)
    else:
        if isinstance(paths, list) and any(isinstance(p, str) and PurePosixPath(p).is_absolute() for p in paths):
            raise ValueError('Submission paths must be repository-relative, e.g. src/package/file.py, not absolute paths')
        if not isinstance(paths, list) or any(not isinstance(p, str) or not implementation_path(p) for p in paths):
            raise ValueError('Select implementation files only; tests and scratch files are excluded')
        known = set(checked(workspace, f'git ls-tree -rz --name-only {base}', exact=True).split('\0')) | candidates
        if any(p not in known for p in paths):
            raise ValueError('Select individual existing/deleted file paths, not directories')
        selected = sorted(set(paths))
    patch = ''
    if selected:
        # Never alter the worker index or indiscriminately git-add the workspace.
        command = ('set -eu; index=$(mktemp); rm "$index"; '
                   'trap \'rm -f "$index"\' EXIT; export GIT_INDEX_FILE="$index"; '
                   f'git read-tree {base}; git add -A -- ' + ' '.join(shlex.quote(p) for p in selected)
                   + f'; git diff --cached --binary --no-ext-diff --no-textconv {base}')
        patch = checked(workspace, command, exact=True)
    return dict(patch=patch, base=base, selected_paths=selected, excluded_paths=sorted(candidates - set(selected)))
