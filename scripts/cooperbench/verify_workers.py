#!/usr/bin/env python3
"""Offline probes of real sanitized worker containers; no model calls."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from benchmarks.cooperbench.native import DockerBackend
from benchmarks.cooperbench.isolation import prepare_worker, verify_worker
from benchmarks.cooperbench.snapshot import capture
from harness.execution import ContainerWorkspace
from native_check import PILOT
from run import TOOL_OUTPUT_LIMIT, SNAPSHOT_OUTPUT_LIMIT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--authorized-local-evaluation', action='store_true', required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    for index, pair in enumerate(PILOT):
        sb = DockerBackend().create_sandbox(pair.image, timeout=600, workdir='/workspace/repo')
        try:
            workspace = ContainerWorkspace(sb.container, '/workspace/repo', timeout=180, output_limit=TOOL_OUTPUT_LIMIT)
            isolation = prepare_worker(workspace)
            base = isolation['base']
            assert workspace.execute('git fsck --lost-found')['exit_code'] == 0
            verify_worker(workspace, base)
            known_future = {'pallets_click_task': '0d69b6ce8b25fe31ea580c608adb8e45df3805bb',
                            'pallets_jinja_task': 'e690f7c5962aea8de43cd09689dcca12bcf29014'}.get(pair.repo)
            if known_future:
                assert workspace.execute('git cat-file -e ' + known_future)['exit_code'] != 0
            tools = {t.name: t for t in workspace.tools()}
            negative = tools['terminal'].run(dict(command='printf "failed test\\n"; exit 1'), None)
            assert negative.meta['exit_code'] == 1 and negative.meta['error'] is False
            source = 'value = ' + repr('x' * 40000) + '\n'
            nested = tools['write_file'].run(dict(path='.cooperbench_scratch/nested/probe.py', content=source), None)
            assert not nested.meta['error'] and nested.meta['exit_code'] == 0
            written = tools['write_file'].run(dict(path='isolation_probe.py', content=source), None)
            assert written.meta['exit_code'] == 0
            assert tools['read_file'].run(dict(path='isolation_probe.py'), None).meta['truncated'] is True
            hashed = tools['read_file'].run(dict(path='isolation_probe.py', metadata_only=True), None)
            assert hashed.meta['exit_code'] == 0 and not hashed.meta['truncated']
            snapshot_workspace = ContainerWorkspace(sb.container, '/workspace/repo', output_limit=SNAPSHOT_OUTPUT_LIMIT)
            snapshot = capture(snapshot_workspace, base, ['isolation_probe.py'])
            assert len(snapshot['patch']) > TOOL_OUTPUT_LIMIT and source.strip() in snapshot['patch']
            timed = ContainerWorkspace(sb.container, '/workspace/repo', timeout=1).execute('sleep 3')
            assert timed['execution_error'] and timed['error_kind'] == 'execution_timeout'
            result = dict(pair=pair.key, isolation=isolation, known_future_unreadable=bool(known_future),
                          nonzero_is_evidence=True, nested_write=True, bounded_read=True,
                          metadata_read=True, large_snapshot=True, timeout_is_execution_error=True, paid_calls=0)
            (args.output / f'{index}.json').write_text(json.dumps(result, indent=2))
            print(json.dumps(result), flush=True)
        finally:
            sb.terminate()


if __name__ == '__main__':
    main()
