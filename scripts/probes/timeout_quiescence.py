"""Free Docker timeout-order probe; synthetic adapter, no native model dispatch."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from benchmarks.kramabench.tasks import Task
from common.io import write_json
from harness.runtime_support.resources import ContainerResources
from scripts.kramabench import cli_runtime as krama


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--image', default=krama.runtime.DEFAULT_SOLVER_IMAGE)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps(dict(status='planned', paid_calls=0)))
        return
    ids = subprocess.check_output(['docker', 'ps', '-q'], text=True).split()
    allocated = sum(r['HostConfig']['NanoCpus'] / 1e9 for r in json.loads(
        subprocess.check_output(['docker', 'inspect', *ids], text=True))) if ids else 0
    if allocated + 8 > (os.cpu_count() or 1):
        raise RuntimeError('No spare CPU8 reservation for the free probe')
    os.umask(0o077)
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    args.upstream = args.output/'inputs'
    (args.upstream/'data').mkdir(parents=True)
    args.record_resources, args.cpus, args.timeout = True, 8, 1
    backend = 'claude-code-single-agent'
    marker = args.output/'synthetic'/backend/'workspace/heartbeat'
    observations = {}

    class Adapter:
        def __init__(self, *unused): pass

        def run(self, *unused, **kwargs):
            code = "import time\nf=open('/workspace/heartbeat','ab',buffering=0)\nwhile True:\n f.write(b'x'); time.sleep(.02)\n"
            child = subprocess.Popen([*kwargs['command_prefix'], 'python3', '-c', code],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                deadline = time.monotonic() + 10
                while not marker.exists() or marker.stat().st_size < 2:
                    if time.monotonic() > deadline:
                        raise TimeoutError('Synthetic writer did not start')
                    time.sleep(.02)
            finally:
                child.terminate()
                try: child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
            before = marker.stat().st_size
            time.sleep(.15)
            observations['writer_survived_exec_client_exit'] = marker.stat().st_size > before
            return dict(status='timed_out')

    class DelayedResources(ContainerResources):
        def close(self, **kwargs):
            if self.result is None:
                state = json.loads(subprocess.check_output(
                    ['docker', 'inspect', '--format', '{{json .State}}', self.identity], text=True, timeout=15))
                observations['stopped_before_resource_close'] = not state['Running']
                before = marker.stat().st_size
                time.sleep(.3)
                observations['heartbeat_stable_during_slow_resource_close'] = marker.stat().st_size == before
            return super().close(**kwargs)

    with patch.object(krama, 'ClaudeCodeSingleAgentCLI', Adapter), patch.object(krama, 'ContainerResources', DelayedResources):
        report = krama.run_attempt(Task('synthetic', 'astronomy', 'Synthetic timeout check'), backend,
            args, 'synthetic-not-a-provider-key', threading.Event(), set(), threading.Lock())
    result = dict(passed=report['status'] == 'timed_out' and all(observations.values()),
        paid_calls=0, real_credentials=False, native_cli_exercised=False, network='none',
        status=report['status'], observations=observations, cleanup=report.get('cleanup'),
        scope='Docker exec survival and container shutdown ordering; not native provider behavior')
    write_json(args.output/'proof.json', result)
    print(json.dumps(result))
    raise SystemExit(0 if result['passed'] else 1)


if __name__ == '__main__':
    main()
