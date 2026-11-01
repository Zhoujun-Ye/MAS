"""Adapter-side snapshots; never injected into a model conversation."""

import json
from pathlib import Path
import subprocess
import sys


SNAPSHOT_SCRIPT = r'''
import hashlib, json, os, pathlib, subprocess
os.environ['GIT_OPTIONAL_LOCKS'] = '0'
def git(*args):
    return subprocess.check_output(['git', *args])
root = pathlib.Path(git('rev-parse', '--show-toplevel').decode().strip())
os.chdir(root)
files = {}
names = set(git('ls-files', '-z', '--cached', '--others', '--exclude-standard').split(b'\0'))
for raw in sorted(names):
    if not raw:
        continue
    name = os.fsdecode(raw)
    path = root / name
    try:
        if path.is_symlink():
            files[name] = {'kind': 'symlink', 'sha256': hashlib.sha256(os.fsencode(os.readlink(path))).hexdigest()}
        elif path.is_file():
            if not path.resolve().is_relative_to(root):
                raise RuntimeError('File escapes workspace: ' + name)
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(1048576), b''):
                    digest.update(block)
            files[name] = {'kind': 'file', 'sha256': digest.hexdigest()}
        else:
            files[name] = {'kind': 'missing_or_directory'}
    except FileNotFoundError:
        files[name] = {'kind': 'changed_during_snapshot'}
head_result = subprocess.run(['git', 'rev-parse', '--verify', 'HEAD'], capture_output=True)
head = head_result.stdout.decode().strip() if head_result.returncode == 0 else None
branch_result = subprocess.run(['git', 'symbolic-ref', '-q', 'HEAD'], capture_output=True)
head_ref = branch_result.stdout.decode().strip() if branch_result.returncode == 0 else None
refs = dict(line.decode().split('\0', 1) for line in git('for-each-ref', '--format=%(refname)%00%(objectname)').splitlines())
diff = git('diff', '--no-ext-diff', '--no-textconv', '--binary', *(['HEAD'] if head else []), '--')
status = git('status', '--porcelain=v1', '-z', '--untracked-files=all')
print(json.dumps({'files': files, 'head': head, 'head_ref': head_ref, 'refs': refs,
                  'optional_locks': False, 'diff_sha256': hashlib.sha256(diff).hexdigest(),
                  'status_entries': [os.fsdecode(x) for x in status.split(b'\0') if x],
                  'atomic': False, 'scope': 'tracked_and_nonignored_untracked'}))
'''


class GitWorkspaceAudit:
    def __init__(self, root: Path, timeout=60):
        self.root = Path(root)
        self.timeout = timeout

    def __call__(self, *, timeout=None):
        result = subprocess.run([sys.executable, "-c", SNAPSHOT_SCRIPT], cwd=self.root,
                                capture_output=True, text=True, check=True,
                                timeout=self.timeout if timeout is None else min(self.timeout, timeout))
        return json.loads(result.stdout)
