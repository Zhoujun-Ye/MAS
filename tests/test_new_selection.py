import copy
import json

import pytest

from benchmarks.cooperbench.adapter import Pair
from benchmarks.cooperbench.selection import expansion, started_inventory, validate_expansion


@pytest.fixture
def inventory(tmp_path):
    dataset = tmp_path / 'dataset'
    (dataset / 'subsets').mkdir(parents=True)
    tasks = [dict(repo=f'repo{r}_task', task_id=t, pairs=[[1, f] for f in range(2, 24)])
             for r in range(3) for t in range(2)]
    (dataset / 'subsets/all.json').write_text(json.dumps(dict(tasks=tasks)))
    outputs = tmp_path / 'outputs'
    outputs.mkdir()
    return dataset, outputs


def start(outputs, pair, name='old'):
    folder = outputs / name / '0'
    folder.mkdir(parents=True)
    (folder / 'manifest.json').write_text(json.dumps(dict(pair=pair)))
    return folder


def test_selection_balanced_deterministic_excludes_failed_and_unfinished(inventory):
    dataset, outputs = inventory
    old = dict(repo='repo0_task', task_id=0, features=[1, 2])
    start(outputs, old)  # No result: even an unfinished run must be excluded.
    excluded, receipts = started_inventory(outputs)
    selected = expansion(dataset, excluded, receipts)
    assert selected == expansion(dataset, excluded, receipts)
    assert len(selected['pairs']) == 100
    assert old not in json.loads(json.dumps(selected['pairs']))
    assert len({(p['repo'], p['task_id']) for p in selected['pairs']}) == 6
    counts = [sum(p['repo'] == f'repo{r}_task' for p in selected['pairs']) for r in range(3)]
    assert max(counts) - min(counts) == 1
    validate_expansion(json.loads(json.dumps(selected)), dataset, outputs)
    tampered = copy.deepcopy(selected)
    tampered['pairs'].reverse()
    with pytest.raises(ValueError, match='sampling rule'):
        validate_expansion(tampered, dataset, outputs)


def test_reject_newly_started_pairs_unless_explicit_continuation(inventory):
    dataset, outputs = inventory
    selection = expansion(dataset, *started_inventory(outputs))
    pair = selection['pairs'][0]
    folder = start(outputs, pair, 'new')
    with pytest.raises(ValueError, match='inventory changed'):
        validate_expansion(selection, dataset, outputs)
    key = Pair(pair['repo'], pair['task_id'], tuple(pair['features'])).key
    validate_expansion(selection, dataset, outputs, {key})
    with pytest.raises(ValueError, match='Invalid continuation'):
        validate_expansion(selection, dataset, outputs, {'not-selected'})


def test_predecessor_receipts_cannot_be_changed(inventory):
    dataset, outputs = inventory
    folder = start(outputs, dict(repo='repo0_task', task_id=0, features=[1, 2]))
    selection = expansion(dataset, *started_inventory(outputs))
    (folder / 'manifest.json').write_text(json.dumps(dict(pair=dict(repo='repo0_task', task_id=0, features=[1, 3]))))
    with pytest.raises(ValueError, match='evidence changed'):
        validate_expansion(selection, dataset, outputs)


def test_insufficient_inventory_fails_closed(inventory):
    dataset, outputs = inventory
    with pytest.raises(ValueError, match='Insufficient'):
        expansion(dataset, set(), {}, count=133)
