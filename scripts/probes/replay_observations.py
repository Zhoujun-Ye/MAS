"""Offline replay of affected native hook events, without executing their tools."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from common.io import write_json
from harness.evidence_mas.hook import collect
from harness.evidence_mas.store import Store
import harness.evidence_mas.store as store_module
import harness.evidence_mas.hook as hook_module


def replay(run):
    summary=json.loads((run/'summary.json').read_text())
    results=[]
    for item in summary['rows']:
        folder=Path(item['run'])/item['task_id']/item.get('runtime_backend',item['backend'])
        if not (folder/'native-profile/evidence/degraded.jsonl').is_file():
            continue
        errors={}
        with tempfile.TemporaryDirectory(prefix='mas-capture-replay-') as tmp:
            store=Store(Path(tmp)/'store','offline-replay')
            with (folder/'native-profile/observer/events.jsonl').open() as stream:
                for line in stream:
                    try:
                        collect(store,json.loads(line))
                    except Exception as error:
                        # Codes only: never copy private event contents into reports.
                        code=getattr(error,'code',type(error).__name__)
                        errors[code]=errors.get(code,0)+1
            with store.connect() as db:
                observations=store.latest(db,'observation')
                integrity=db.execute('PRAGMA integrity_check').fetchone()[0]
            transformed=[o for o in observations if o.get('input_transform')=='native_send_message_alias_pruning']
            results.append(dict(benchmark=item['benchmark'],task_id=item['task_id'],mode=item['backend'],
                errors=errors,integrity=integrity,reconciled_send_messages=len(transformed),
                raw_inputs_preserved=all(store.read_blob(o['input_ref'])!=store.read_blob(o['terminal_input_ref']) for o in transformed)))
    return dict(passed=bool(results) and all(not r['errors'] and r['integrity']=='ok' and r['raw_inputs_preserved'] for r in results),
        cases=results,paid_calls=0,tools_reexecuted=False,original_artifacts_modified=False,
        implementation={Path(m.__file__).name:hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest() for m in (store_module,hook_module)})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    if not args.execute:
        print(json.dumps(dict(status='planned',paid_calls=0,tools_reexecuted=False)))
        return 0
    run,output=args.run.resolve(),args.output.resolve()
    if output.is_relative_to(run) or run.is_relative_to(output):
        raise ValueError('Replay output must not overlap original artifacts')
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    result=replay(run)
    write_json(output/'proof.json',result)
    print(json.dumps(result))
    return 0 if result['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
