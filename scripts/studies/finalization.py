"""Matrix terminal-export recovery in a fresh namespace; never replay a solver."""

import json
from pathlib import Path
import shutil
from types import SimpleNamespace

from benchmarks._external import digest, jsonl, write_jsonl
from common.io import fingerprint, write_json


def needed(benchmark,task,backend,run):
    report=run/task.id/backend/'report.json'
    if not report.exists():
        return False
    record=json.loads(report.read_text())
    if record.get('status') not in {'cli_exited','native_condition_unverified'}:
        return False
    if benchmark=='kramabench':
        path = run / 'summary.json'
        return not path.exists() or json.loads(path.read_text()).get('offline_evaluation_pending', False)
    predictions=run/'predictions.jsonl'
    if not predictions.exists():
        return True
    rows=jsonl(predictions)
    return len(rows)!=1 or rows[0]!=record


def recover(benchmark,task,backend,run,target,*,root,image):
    from scripts.common import run as external
    from scripts.kramabench import cli_runtime as krama
    frozen=json.loads((run/'plan.json').read_text())
    if frozen.get('evidence'):
        raise ValueError('Retired FULL/OBS attempts remain read-only; no baseline finalization')
    if benchmark=='kramabench':
        if fingerprint(krama.verify_inputs(root/benchmark/'upstream'))!=frozen['inputs_sha256']:
            raise ValueError('Frozen recovery inputs changed')
    else:
        for path,expected in frozen['assets'].items():
            if isinstance(expected,dict):
                from benchmarks._external import asset_manifest
                actual=asset_manifest(Path(path))
            else:
                actual=digest(Path(path))
            if actual!=expected:
                raise ValueError('Frozen recovery inputs changed')
    # Copy only into a fresh run-owned namespace; old raw evidence stays intact.
    shutil.copytree(run,target,symlinks=True,ignore=lambda parent,names:[
        name for name in names if (Path(parent)/name).is_socket()])
    folder=target/task.id/backend
    report=json.loads((folder/'report.json').read_text())
    args=SimpleNamespace(backend=backend,image=image,
                         cpus=frozen.get('cpu_per_attempt',2),compute_threads=frozen.get('compute_threads',1),
                         upstream=root/benchmark/'upstream',replay_timeout=180)
    if benchmark=='kramabench':
        replay=folder/'replay-workspace'
        if replay.is_symlink():
            raise ValueError('Nonregular recovery replay workspace')
        if replay.exists():
            shutil.rmtree(replay)
        report=krama.collect_attempt(folder,report,args)
        write_json(target/'summary.json',dict(plan=frozen,rows=[report],paid_judge_calls=0,
            billing=json.loads((run/'solver-billing.json').read_text()) if (run/'solver-billing.json').exists() else None,
            offline_finalization=True))
    else:
        report=external.finalize_attempt(folder,args,report)
        write_jsonl(target/'predictions.jsonl',[report],replace=True)
    write_json(target/'offline-finalization.json',dict(original_run=str(run),
        original_report_sha256=digest(run/task.id/backend/'report.json'),model_calls=0))
    return report
