"""Outcome-independent selection from the pinned public subset inventory."""
import hashlib
import json
from dataclasses import asdict

from .adapter import Pair, REVISION

SEED = 'cooperbench-20-20261030'
OBSERVED = {('pallets_click_task', 2068, (1, 4)), ('pallets_jinja_task', 1465, (1, 7)),
            ('samuelcolvin_dirty_equals_task', 43, (2, 3))}


def rank(value):
    return hashlib.sha256((SEED + ':' + value).encode()).hexdigest()


def choose(dataset, count=20):
    subset = dataset / 'subsets/lite.json'
    groups = {}
    for task in json.loads(subset.read_text())['tasks']:
        for features in task['pairs']:
            pair = Pair(task['repo'], int(task['task_id']), tuple(features))
            if (pair.repo, pair.task_id, pair.features) not in OBSERVED:
                groups.setdefault(pair.repo, []).append(pair)
    for rows in groups.values():
        rows.sort(key=lambda p: rank(p.key))
    repos = sorted(groups, key=rank)
    selected = []
    depth = 0
    while len(selected) < count:
        available = [groups[r][depth] for r in repos if depth < len(groups[r])]
        if not available:
            raise ValueError('Insufficient unobserved pairs')
        selected.extend(available[:count - len(selected)])
        depth += 1
    return dict(revision=REVISION, seed=SEED, selection='repo-stratified-round-robin-hash-v1',
                subset_sha256=hashlib.sha256(subset.read_bytes()).hexdigest(),
                previously_observed_pairs_excluded=True, pairs=[asdict(p) for p in selected])


def load_selection(path):
    data = json.loads(path.read_text())
    if data['revision'] != REVISION:
        raise ValueError('Selection revision mismatch')
    pairs = [Pair(p['repo'], int(p['task_id']), tuple(p['features'])) for p in data['pairs']]
    if not pairs or len({p.key for p in pairs}) != len(pairs):
        raise ValueError('Selection contains duplicate or no pairs')
    return pairs


def lite(dataset):
    subset = dataset / 'subsets/lite.json'
    pairs = [Pair(t['repo'], int(t['task_id']), tuple(p))
             for t in json.loads(subset.read_text())['tasks'] for p in t['pairs']]
    if len(pairs) != 100 or len({p.key for p in pairs}) != 100:
        raise ValueError('Expected exactly 100 official lite pairs')
    return dict(revision=REVISION, selection='official-lite-complete-v1',
                subset_sha256=hashlib.sha256(subset.read_bytes()).hexdigest(),
                previously_observed_pairs_excluded=False, pairs=[asdict(p) for p in pairs])


def all_task_pairs(dataset):
    return [Pair(t['repo'], int(t['task_id']), tuple(t['pairs'][0]))
            for t in json.loads((dataset / 'subsets/all.json').read_text())['tasks']]
