import json
import subprocess
from types import SimpleNamespace

import pytest

from benchmarks.cooperbench.adapter import Pair
from scripts.cooperbench.pilot import cleanup_worker, prior_attempts


def test_cleanup_retries_disposal_and_retains_stderr(monkeypatch):
    monkeypatch.setattr('scripts.cooperbench.pilot.time.sleep', lambda _: None)
    calls = []
    def terminate():
        calls.append(1)
        if len(calls) < 2:
            raise subprocess.CalledProcessError(1, ['docker', 'rm'], stderr=b'resource busy')
    result = cleanup_worker(SimpleNamespace(container='owned-fixture', terminate=terminate))
    assert result['removed'] and len(calls) == 2
    assert result['errors'][0]['stderr'] == 'resource busy'


def test_cleanup_persistent_failure_is_not_hidden(monkeypatch):
    monkeypatch.setattr('scripts.cooperbench.pilot.time.sleep', lambda _: None)
    def terminate():
        raise RuntimeError('daemon unavailable')
    result = cleanup_worker(SimpleNamespace(container='owned-fixture', terminate=terminate))
    assert not result['removed'] and len(result['errors']) == 3


def test_continuation_skips_failed_paid_attempts_without_reusing_scores(tmp_path):
    pairs = [Pair('fixture_task', 0, (1, i)) for i in (2, 3, 4)]
    selection = dict(pairs=[p.key for p in pairs])
    (tmp_path / 'pilot-manifest.json').write_text(json.dumps(dict(selection=selection)))
    (tmp_path / 'pilot-summary.json').write_text(json.dumps([
        dict(index=0, pair=pairs[0].key, paid_attempts=1, grade=False),
        dict(index=1, pair=pairs[1].key, paid_attempts=0, not_started=True)]))
    (tmp_path / 'batch-accounting.json').write_text('{}')
    skipped, receipts = prior_attempts([tmp_path], pairs, selection)
    assert skipped == {0}
    assert receipts[str(tmp_path.resolve())]['started_indices'] == [0]
    assert len(receipts[str(tmp_path.resolve())]['evidence_sha256']) == 3
    with pytest.raises(ValueError, match='Duplicate'):
        prior_attempts([tmp_path, tmp_path], pairs, selection)
    with pytest.raises(ValueError, match='selection differs'):
        prior_attempts([tmp_path], pairs, {})
    (tmp_path / 'batch-accounting.json').unlink()
    with pytest.raises(ValueError, match='not finished'):
        prior_attempts([tmp_path], pairs, selection)


def test_continuation_requires_all_predecessors(tmp_path):
    (tmp_path / 'pilot-manifest.json').write_text(json.dumps(dict(selection={},
        continued_batches={'/missing-first-segment': {}})))
    with pytest.raises(ValueError, match='complete predecessor chain'):
        prior_attempts([tmp_path], [], {})
