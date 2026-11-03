import hashlib
import json

import pytest

from scripts.kramabench.retain_current import retain


def fixture(root):
    publication = root/'publication'
    publication.mkdir(parents=True)
    rows = []
    for backend in ('deepagents','claude-code'):
        folder = root/'raw'/'task'/backend
        folder.mkdir(parents=True)
        payload = b'{"answer":1}'
        (folder/'submission.json').write_bytes(payload)
        (folder/'report.json').write_text('{"status":"cli_exited"}')
        rows.append(dict(task_id='task',backend=backend,source_run=str(root/'raw'),
                         grade=dict(submission_file_sha256=hashlib.sha256(payload).hexdigest())))
    data = dict(rows=rows,cohorts=dict(single={},team={}),source_audits={})
    (publication/'summary.json').write_text(json.dumps(data))
    (publication/'REPORT.md').write_text('selected results')
    (root/'older').mkdir()
    return publication


def test_cleanup_is_planned_by_default_and_retains_exact_evidence(tmp_path):
    root = tmp_path/'outputs'
    publication = fixture(root)
    archive = tmp_path/'archives'/'old'
    plan = retain(root,publication,archive,expected_tasks=1)
    assert plan['status'] == 'planned' and not archive.exists()
    result = retain(root,publication,archive,execute=True,expected_tasks=1)
    assert result['permanently_deleted'] == 0
    assert sorted(p.name for p in root.iterdir()) == ['current']
    assert (archive/'older').is_dir()
    assert (archive/'raw/task/claude-code/submission.json').read_bytes() == b'{"answer":1}'
    current = json.loads((root/'current/comparison/summary.json').read_text())
    assert {r['backend'] for r in current['rows']} == {'deepagents','claude-code-agent-team'}
    assert (root/'current/evidence/task/claude-code-agent-team/submission.json').is_file()
    with pytest.raises(FileExistsError):
        retain(root,publication,archive,execute=True,expected_tasks=1)


def test_reports_only_cleanup_never_copies_remote_evidence(tmp_path):
    root = tmp_path/'outputs'
    publication = fixture(root)
    value = retain(root,publication,tmp_path/'archive',execute=True,reports_only=True,expected_tasks=1)
    assert value['copied_evidence'] == 0
    assert (root/'current/comparison/REPORT.md').is_file()
    assert not (root/'current/evidence').exists()
