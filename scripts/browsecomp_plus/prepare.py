#!/usr/bin/env python3
"""Verify retained official assets read-only and freeze an outcome-blind sample."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from benchmarks.browsecomp_plus.adapter import ROOT as BENCH, INDEX, JAVA, task_rows, select_sample


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def main():
    output = BENCH / 'assets/team-prepared-v1.json'
    if output.exists():
        raise SystemExit('Prepared manifest already exists; do not replace a frozen sample')
    rows = task_rows()
    assets = INDEX.parent / 'assets.json'
    provenance = json.loads(assets.read_text())
    for item in provenance['index_files']:
        path = INDEX.parent / item['path']
        if path.stat().st_size != item['size'] or sha(path) != item['sha256']:
            raise ValueError('Index verification failed: ' + str(path))
    qrels = BENCH / 'upstream/topics-qrels/qrel_evidence.txt'
    official_ids = {line.split()[0] for line in qrels.read_text().splitlines() if line.strip()}
    if {str(r['query_id']) for r in rows} != official_ids:
        raise ValueError('Test IDs do not match the pinned official evidence qrels')
    excluded = set()
    for old in (ROOT / 'outputs/browsecomp_plus', ROOT / 'outputs/bcp'):
        for path in old.glob('*/results/*.json'):
            row = json.loads(path.read_text())
            excluded.add(str(row.get('task_id', row.get('query_id'))))
    selected = select_sample(rows, excluded)
    if len(selected) != 6:
        raise ValueError('Need six eligible queries')
    manifest = dict(split='official test', total=830, source_sha=sha(BENCH / 'assets/tasks.jsonl'),
                    data_provenance=json.loads((BENCH / 'assets/tasks.provenance.json').read_text()),
                    index=str(INDEX), index_provenance_sha=sha(assets), index_revision=provenance['index_revision'],
                    java_home=str(JAVA), java_release_sha=sha(JAVA / 'release'),
                    upstream_commit=subprocess.check_output(['git', '-C', str(BENCH / 'upstream'), 'rev-parse', 'HEAD'], text=True).strip(),
                    qrels_sha=sha(qrels), excluded_historical_ids=sorted(excluded),
                    selection='query chars 150..1600; exclude previous project runs; sort SHA256(bcp-team-20261029:query_id); first six; no answers/outcomes used',
                    task_ids=[str(r['query_id']) for r in selected])
    with output.open('x') as f:
        json.dump(manifest, f, indent=2)
    print(json.dumps(dict(prepared=str(output), task_ids=manifest['task_ids'], verified_index_files=len(provenance['index_files']))))


if __name__ == '__main__':
    main()
