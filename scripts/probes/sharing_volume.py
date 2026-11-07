"""Offline hook replay: measure delivery volume, never replay tools or models."""

import argparse
import json
from pathlib import Path
import sys
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--events', type=Path, nargs='+', required=True)
    parser.add_argument('--implementation-root', type=Path,
                        default=Path(__file__).resolve().parents[2])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps(dict(status='planned', files=len(args.events), paid_calls=0)))
        return
    if args.output.exists():
        raise FileExistsError(args.output)
    sys.path.insert(0,str(args.implementation_root.resolve()))
    from harness.evidence_mas.store import Store
    from harness.evidence_mas import hook, sharing
    from common.io import write_json
    from benchmarks._external import digest

    results = []
    for path in args.events:
        started = time.monotonic()
        characters = emissions = references = blocked = 0
        with tempfile.TemporaryDirectory(prefix='mas-sharing-replay-') as temporary:
            store = Store(Path(temporary)/'store','offline-volume')
            for line in path.read_text().splitlines():
                event = json.loads(line)
                # Evaluate guards, but retain the actual event stream: no counterfactual
                # solver behavior or wall-time saving can be inferred from this replay.
                if hasattr(hook,'wait_guard') and hook.wait_guard(store,event):
                    blocked += 1
                hook.collect(store,event)
                response = sharing.context_reply(store,event,'full')
                if not response:
                    continue
                text = response['hookSpecificOutput']['additionalContext']
                emissions += 1
                characters += len(text)
                references += len(json.loads(text.split('\n')[-1])['observations'])
        results.append(dict(events=str(path),events_sha256=digest(path),characters=characters,
                            emissions=emissions,observation_references=references,
                            completed_worker_waits_rejected=blocked,
                            replay_seconds=time.monotonic()-started))
    receipt = dict(policy=sharing.POLICY,implementation_root=str(args.implementation_root),
                   source_sha256={name:digest(args.implementation_root/'harness/evidence_mas'/name)
                                  for name in ('sharing.py','hook.py','cli.py')},
                   results=results,paid_calls=0,tools_executed=0,
                   scope='Same recorded event order, synthetic stores; context volume only, not model behavior or speedup')
    write_json(args.output,receipt)
    print(json.dumps(receipt))


if __name__=='__main__':
    main()
