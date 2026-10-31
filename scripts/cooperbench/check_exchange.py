#!/usr/bin/env python3
"""Exercise exact file exchange in real sanitized workers without model calls."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from benchmarks.cooperbench.adapter import make_team, verify_checkout
from benchmarks.cooperbench.selection import load_selection
from benchmarks.cooperbench.native import DockerBackend
from benchmarks.cooperbench.isolation import prepare_worker
from harness.execution import ContainerWorkspace
from harness.llm import ModelConfig
from harness.trace import Trace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selection', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--authorized-local-evaluation', action='store_true', required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    pair = load_selection(args.selection)[0]
    sandboxes = []
    try:
        spaces = {}
        for role in ('worker_a', 'worker_b'):
            sb = DockerBackend().create_sandbox(pair.image, timeout=600, workdir='/workspace/repo')
            sandboxes.append(sb)
            spaces[role] = ContainerWorkspace(sb.container, '/workspace/repo', output_limit=200000)
            prepare_worker(spaces[role])
        with Trace(args.output / 'trace.jsonl', 'offline-exchange') as trace:
            team = make_team(pair, verify_checkout(), spaces, SimpleNamespace(cfg=ModelConfig(model='offline-scripted')), trace)
            team.agents = {r: SimpleNamespace(name=r, messages=[]) for r in (*spaces, 'leader')}
            content = '# exact transfer\n' + 'value = "a\\nb"\n' * 4000
            path = 'collaboration_transport_probe.py'
            result = spaces['worker_a'].tools()[2].run(dict(path=path, content=content), None)
            assert result.meta['exit_code'] == 0
            team.domain['share_files'].run(dict(recipient='worker_b', paths=[path]), team.agents['worker_a'])
            assert 'a1' not in team.access['leader']
            result = team.domain['import_files'].run(dict(id='a1'), team.agents['worker_b'])
            assert not result.meta.get('error'), result
            result = spaces['worker_b'].execute('cat ' + path)
            assert result['exit_code'] == 0 and result['output'] == content
            (args.output / 'summary.json').write_text(json.dumps(dict(passed=True, paid_calls=0,
                exact_transfer_bytes=len(content.encode()), leader_not_granted=True, pair=pair.key)))
    finally:
        for sb in sandboxes:
            sb.terminate()


if __name__ == '__main__':
    main()
