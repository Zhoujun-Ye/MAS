"""Outcome-blind extension of the frozen twenty by ten pinned public questions."""
import random

from common.io import read_json
from benchmarks.kramabench.tasks import load_tasks
from scripts.studies.benchmark_matrix import task_fingerprint
from scripts.studies.krama_repeats import MANIFEST

SAMPLE_SEED=20261112


def selected_tasks(root):
    pool=load_tasks(root/'kramabench/upstream')[0]
    base=read_json(MANIFEST)['benchmarks']['kramabench']
    lookup={t.id:t for t in pool}
    if len(base)!=20 or any(task_fingerprint('kramabench',lookup[r['task_id']])!=r['task_sha256'] for r in base):
        raise ValueError('Original twenty public task hashes changed')
    original=[lookup[r['task_id']] for r in base]
    remainder=sorted((t for t in pool if t.id not in {x.id for x in original}),key=lambda t:t.id)
    tasks=original+random.Random(SAMPLE_SEED).sample(remainder,10)
    manifest=dict(kind='native-causal30-v1',selection='frozen20_plus_ten_without_replacement_no_outcome_filter',
        sampling_seed=SAMPLE_SEED,benchmarks=dict(kramabench=[dict(task_id=t.id,task_sha256=task_fingerprint('kramabench',t)) for t in tasks]))
    return tasks,manifest
