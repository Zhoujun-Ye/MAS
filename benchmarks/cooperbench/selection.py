"""Outcome-independent selection from the pinned public subset inventory."""
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

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


EXPANSION_SEED = 'cooperbench-new100-20261031'


def started_inventory(root):
    """Read identities, never scores; failed/unfinished attempts also count."""
    keys, receipts = set(), {}
    root = Path(root)
    for path in sorted(root.glob('**/manifest.json')):
        data = json.loads(path.read_text())
        if 'pair' not in data:
            continue
        p = data['pair']
        keys.add(Pair(p['repo'], int(p['task_id']), tuple(p['features'])).key)
        receipts[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return keys, receipts


def expansion(dataset, excluded, receipts, count=100):
    """Round-robin repositories and their tasks without consulting outcomes."""
    subset = dataset / 'subsets/all.json'
    groups = {}
    order = lambda value: hashlib.sha256((EXPANSION_SEED + ':' + value).encode()).hexdigest()
    for task in json.loads(subset.read_text())['tasks']:
        for features in task['pairs']:
            p = Pair(task['repo'], int(task['task_id']), tuple(features))
            if p.key not in excluded:
                groups.setdefault(p.repo, {}).setdefault(p.task_id, []).append(p)
    queues = {}
    for repo, tasks in groups.items():
        task_order = sorted(tasks, key=lambda t: order(repo + '/' + str(t)))
        for values in tasks.values():
            values.sort(key=lambda p: order(p.key))
        queues[repo] = [tasks[t][depth] for depth in range(max(map(len, tasks.values())))
                        for t in task_order if depth < len(tasks[t])]
    repos = sorted(queues, key=order)
    ranked = [queues[r][depth] for depth in range(max(map(len, queues.values()), default=0))
              for r in repos if depth < len(queues[r])]
    if count <= 0 or len(ranked) < count:
        raise ValueError('Insufficient unstarted official pairs')
    return dict(revision=REVISION, selection='new-official-repo-task-round-robin-v1',
                seed=EXPANSION_SEED, count=count, benchmark_profile='clarified-v1',
                subset_sha256=hashlib.sha256(subset.read_bytes()).hexdigest(),
                excluded_started_pairs=sorted(excluded), predecessor_manifests=receipts,
                pairs=[asdict(p) for p in ranked[:count]])


def validate_expansion(data, dataset, outputs, allowed_started=()):
    expected = expansion(dataset, set(data['excluded_started_pairs']), data['predecessor_manifests'])
    if json.dumps(data, sort_keys=True) != json.dumps(expected, sort_keys=True):
        raise ValueError('Expansion selection differs from its frozen sampling rule')
    current, receipts = started_inventory(outputs)
    if any(receipts.get(path) != sha for path, sha in data['predecessor_manifests'].items()):
        raise ValueError('Predecessor evidence changed')
    selected = {Pair(p['repo'], p['task_id'], tuple(p['features'])).key for p in data['pairs']}
    if not set(allowed_started) <= selected:
        raise ValueError('Invalid continuation exclusion')
    if not current - set(allowed_started) <= set(data['excluded_started_pairs']):
        raise ValueError('Started inventory changed; freeze a fresh selection before payment')
    if selected & (current - set(allowed_started)):
        raise ValueError('Expansion would rerun an already started pair')
