import subprocess
from types import SimpleNamespace

import pytest

from benchmarks.cooperbench.adapter import Pair, make_team
from harness.execution import ContainerWorkspace
from harness.trace import Trace
from fakes import ScriptedClient


def test_exact_patch_exchange_and_acl(tmp_path, monkeypatch):
    from benchmarks.cooperbench import adapter
    roots = {}
    for name in ('worker_a', 'worker_b'):
        root = tmp_path / name
        root.mkdir()
        roots[name] = root
        subprocess.run(['git', 'init', '-q', str(root)], check=True)
        (root / 'source.py').write_text('value = 1\n')
        subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(root), '-c', 'user.name=Fixture', '-c',
                        'user.email=fixture@example.invalid', 'commit', '-qm', 'base'], check=True,
                       env=__import__('os').environ | {'GIT_AUTHOR_DATE': '2020-01-01T00:00:00Z',
                                                     'GIT_COMMITTER_DATE': '2020-01-01T00:00:00Z'})

    class Workspace(ContainerWorkspace):
        def execute(self, command, stdin=None, **kwargs):
            result = subprocess.run(command, input=stdin, text=True, shell=True,
                                    cwd=roots[self.container], capture_output=True, timeout=10)
            return dict(exit_code=result.returncode, output=result.stdout + result.stderr, truncated=False)

    monkeypatch.setattr(adapter, 'ContainerWorkspace', Workspace)
    monkeypatch.setattr(Pair, 'private_inputs', lambda *a: {})
    spaces = {r: Workspace(r) for r in roots}
    with Trace(tmp_path / 'trace.jsonl', 'exchange') as trace:
        team = make_team(Pair('fixture_task', 0, (1, 2)), tmp_path, spaces,
                         ScriptedClient(lambda *a: {}), trace)
        team.agents = {r: SimpleNamespace(name=r, messages=[]) for r in (*roots, 'leader')}
        a, b = team.agents['worker_a'], team.agents['worker_b']
        content = '# large change\n' + 'value = "exact\\ntext"\n' * 3000
        (roots['worker_a'] / 'source.py').write_text(content)
        team.domain['share_files'].run(dict(recipient='worker_b', paths=['source.py']), a)
        (roots['worker_a'] / 'source.py').write_text('changed after sharing\n')
        with pytest.raises(ValueError, match='not granted'):
            team.domain['import_files'].run(dict(id='a1'), team.agents['leader'])
        result = team.domain['import_files'].run(dict(id='a1'), b)
        assert not result.meta.get('error')
        assert (roots['worker_b'] / 'source.py').read_text() == content
        conflict = team.domain['import_files'].run(dict(id='a1'), b)
        assert conflict.meta['error_kind'] == 'patch_conflict'
        assert (roots['worker_b'] / 'source.py').read_text() == content


def test_official_lite_inventory():
    from benchmarks.cooperbench.selection import lite
    from benchmarks.cooperbench.adapter import UPSTREAM
    result = lite(UPSTREAM / 'dataset')
    assert len(result['pairs']) == 100
    assert not result['previously_observed_pairs_excluded']


def test_lite_authorization_accepts_json_roundtrip_and_rejects_changes():
    import json
    from benchmarks.cooperbench.selection import lite
    from benchmarks.cooperbench.adapter import UPSTREAM
    from scripts.cooperbench.pilot import validate_lite_selection
    dataset = UPSTREAM / 'dataset'
    selection = json.loads(json.dumps(lite(dataset)))
    validate_lite_selection(selection, dataset)
    with pytest.raises(ValueError, match='fresh attempts'):
        validate_lite_selection(selection, dataset, [('old-run', 'old-grade')])
    selection['pairs'][0]['features'][0] += 100
    with pytest.raises(ValueError, match='complete official selection'):
        validate_lite_selection(selection, dataset)
