import json
from pathlib import Path

import pytest

from benchmarks._external import digest
from scripts.studies import rescore_validation20_hdr as study


@pytest.mark.parametrize('canonical', [True, False])
def test_recover_binds_existing_answer_and_never_mutates_source(tmp_path, monkeypatch, canonical):
    task = 'sql2s_103'
    folder = tmp_path / task / study.BACKEND
    folder.mkdir(parents=True)
    (tmp_path / 'plan.json').write_text(json.dumps(dict(task_ids=[task])))
    (tmp_path / 'predictions.jsonl').write_text('{}\n')
    report = dict(cli=dict(status='cli_exited', returncode=0, native_result=dict(result='Saved CLI answer')))
    if canonical:
        (folder / 'submission.json').write_text(json.dumps(dict(final_answer='Saved submission')))
        report['submission_sha256'] = digest(folder / 'submission.json')
    (folder / 'report.json').write_text(json.dumps(report))
    monkeypatch.setattr(study, 'native_subagents', lambda *a: dict(passed=True))
    before = {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    _, _, answer, receipt = study.recover(tmp_path)
    assert answer == ('Saved submission' if canonical else 'Saved CLI answer')
    assert receipt['origin'] == ('original_hash_bound_submission' if canonical
                                 else 'recovered_cli_final_missing_submission')
    assert before == {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    monkeypatch.setattr(study, 'native_subagents', lambda *a: dict(passed=False))
    with pytest.raises(ValueError, match='lifecycle'):
        study.recover(tmp_path)
    monkeypatch.setattr(study, 'native_subagents', lambda *a: dict(passed=True))
    if canonical:
        (folder / 'submission.json').write_text(json.dumps(dict(final_answer='tampered')))
        with pytest.raises(ValueError, match='hash mismatch'):
            study.recover(tmp_path)
    else:
        report['cli']['status'] = 'timed_out'
        (folder / 'report.json').write_text(json.dumps(report))
        with pytest.raises(ValueError, match='successfully exited'):
            study.recover(tmp_path)
