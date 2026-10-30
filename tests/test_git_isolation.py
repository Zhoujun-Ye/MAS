from pathlib import Path
import shlex
import subprocess

import pytest

from benchmarks.cooperbench.isolation import prepare_worker, verify_worker


def test_future_refs_reflogs_objects_and_lost_found_are_removed(tmp_path):
    repo = tmp_path / 'repo'
    repo.mkdir()
    patches = tmp_path / 'patches'
    patches.mkdir()
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=repo, text=True).strip()
    git('init', '-q')
    git('config', 'user.email', 'offline@example.invalid')
    git('config', 'user.name', 'Offline')
    (repo / 'source.py').write_text('base\n')
    git('add', '.')
    git('commit', '-qm', 'base')
    base = git('rev-parse', 'HEAD')
    (repo / 'source.py').write_text('FUTURE_ANSWER\n')
    git('commit', '-qam', 'future answer')
    future = git('rev-parse', 'HEAD')
    git('tag', 'answer')
    git('remote', 'add', 'origin', 'https://example.invalid/never-used')
    git('checkout', '--detach', base)
    lost = repo / '.git/lost-found/commit'
    lost.mkdir(parents=True)
    (lost / future).write_text('FUTURE_ANSWER')
    class Workspace:
        def execute(self, command):
            command = command.replace('/patches', shlex.quote(str(patches)))
            p = subprocess.run(command, shell=True, cwd=repo, capture_output=True, text=True, timeout=30)
            return dict(exit_code=p.returncode, output=p.stdout + p.stderr, truncated=False)
    workspace = Workspace()
    with pytest.raises(ValueError):
        verify_worker(workspace, base)
    receipt = prepare_worker(workspace)
    assert receipt['version'] == 'base-history-only-v1'
    assert git('rev-parse', 'HEAD') == base and git('show', 'HEAD:source.py') == 'base'
    assert not git('rev-list', '--all', '--not', base)
    assert subprocess.run(['git', 'cat-file', '-e', future], cwd=repo, capture_output=True).returncode != 0
    git('fsck', '--lost-found')
    assert not (repo / '.git/lost-found').exists()
    verify_worker(workspace, base)
    subprocess.run(['git', 'hash-object', '-w', '--stdin'], input='UNREACHABLE_SECRET', text=True,
                   cwd=repo, check=True, capture_output=True)
    with pytest.raises(ValueError, match='recoverable'):
        verify_worker(workspace, base)
