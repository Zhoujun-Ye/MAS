import pytest

from scripts.cooperbench import repair_report


@pytest.fixture
def original(tmp_path, monkeypatch):
    batch = tmp_path / 'batch'
    batch.mkdir()
    for index in range(100):
        folder = batch / str(index)
        folder.mkdir()
        (folder / 'grade.json').write_text('{}')

    def read_run(folder, path):
        index = int(folder.name)
        return ({'pair': {'repo': 'example', 'task_id': index, 'features': [1, 2]}},
                {'status': 'completed'}, {'correct': index < 71})

    monkeypatch.setattr(repair_report, 'read_run', read_run)
    return batch


def test_current_scoreboard_and_failed_replacement_are_not_best_of(original):
    report = repair_report.build_report([original], [])
    assert (report['passed'], report['failed'], report['total']) == (71, 29, 100)
    assert report['protocol_completed'] == 100
    assert report['rows'][99]['effective_correct'] is False
    replacement = ('99', original / '99', original / '99/grade.json')
    revised = repair_report.build_report([original], [replacement])
    assert revised['passed'] == 71 and revised['replaced_indices'] == [99]
    with pytest.raises(ValueError, match='duplicate replacement'):
        repair_report.build_report([original], [replacement, replacement])


def test_reject_overlapping_incomplete_and_mismatched_inputs(original):
    with pytest.raises(ValueError, match='Overlapping'):
        repair_report.build_report([original, original], [])
    with pytest.raises(ValueError, match='same pair'):
        repair_report.build_report([original], [('0', original / '1', original / '1/grade.json')])
    (original / '99/grade.json').unlink()
    (original / '99').rmdir()
    with pytest.raises(ValueError, match='100 unique'):
        repair_report.build_report([original], [])


def test_duplicate_pair_rejected_even_with_distinct_indices(original, monkeypatch):
    monkeypatch.setattr(repair_report, 'read_run', lambda *args:
                        ({'pair': {'repo': 'same'}}, {'status': 'completed'}, {'correct': True}))
    with pytest.raises(ValueError, match='Duplicate original pair'):
        repair_report.build_report([original], [])
