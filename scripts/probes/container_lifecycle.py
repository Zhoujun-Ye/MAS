"""Free interleaved container shutdown check, with no CLI, keys or task data."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common.io import write_json
from harness.runtime_support.runtime import DEFAULT_SOLVER_IMAGE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default=DEFAULT_SOLVER_IMAGE)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps(dict(status='planned', paid_calls=0)));return
    args.output.mkdir(parents=True, exist_ok=False)
    image = json.loads(subprocess.check_output(['docker','image','inspect',args.image]))[0]['Id']
    rows = []
    for init in (False, True, True, False):
        name = 'mas-init-probe-' + uuid.uuid4().hex[:12]
        command = ['docker','run','-d','--name',name,'--network','none','--cpus','8','--memory','8g']
        if init:command += ['--init']
        command += [image,'sleep','infinity']
        try:
            subprocess.run(command,check=True,capture_output=True,timeout=30)
            start = time.monotonic()
            subprocess.run(['docker','stop','--time','2',name],check=True,capture_output=True,timeout=15)
            seconds = time.monotonic()-start
            state = json.loads(subprocess.check_output(['docker','inspect','--format','{{json .State}}',name],timeout=15))
            rows.append(dict(init=init,stop_seconds=seconds,exit_code=state['ExitCode'],running=state['Running']))
        finally:
            subprocess.run(['docker','rm','-f',name],check=True,capture_output=True,timeout=15)
    passed = all(not r['running'] and r['exit_code']==143 for r in rows if r['init'])
    result = dict(passed=passed,paid_calls=0,image_id=image,rows=rows,
                  scope='Idle-container shutdown only, not native SessionEnd or end-to-end model speedup')
    write_json(args.output/'summary.json',result)
    print(json.dumps(result))
    raise SystemExit(0 if passed else 1)


if __name__ == '__main__':main()
