"""Compare pinned SQLite runtimes with identical read-only SQL, without models."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common.io import write_json


PROBE = r'''
import hashlib,json,sqlite3,sys,time
config=json.load(sys.stdin)
c=sqlite3.connect('file:/input.sqlite?mode=ro',uri=True) if config['external'] else sqlite3.connect(':memory:')
features={}
if not config['external']:
    c.executescript('CREATE TABLE events(visit TEXT, kind INTEGER); CREATE TABLE items(visit TEXT);')
    c.executemany('INSERT INTO events VALUES (?,?)',[(str(i),i%3) for i in range(12000)])
    c.executemany('INSERT INTO items VALUES (?)',[(str(i),) for i in range(6000)])
    checks={
        'fts5': "CREATE VIRTUAL TABLE f USING fts5(body)",
        'rtree': "CREATE VIRTUAL TABLE r USING rtree(id,x1,x2)",
        'json': "SELECT json_extract('{\"a\":2}','$.a')",
        'window': 'SELECT row_number() OVER () FROM events LIMIT 1',
        'math': 'SELECT sqrt(4)',
        'update_limit': 'UPDATE events SET kind=kind LIMIT 1',
        'delete_limit': 'DELETE FROM events WHERE kind=-1 LIMIT 1',
    }
    for name,sql in checks.items():
        try:c.execute(sql).fetchall();features[name]=True
        except sqlite3.Error:features[name]=False
c.execute('PRAGMA query_only=ON')
def authorize(action,a,b,db,source):
    if action in (sqlite3.SQLITE_ATTACH,sqlite3.SQLITE_DETACH):return sqlite3.SQLITE_DENY
    if action==sqlite3.SQLITE_FUNCTION and str(b).lower()=='load_extension':return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK
c.set_authorizer(authorize)
results=[]
for sql in config['queries']:
    start=time.monotonic(); cpu=time.process_time()
    c.set_progress_handler(lambda:int(time.monotonic()-start>config['timeout']),10000)
    row=dict(query_sha256=hashlib.sha256(sql.encode()).hexdigest())
    try:
        plan=c.execute('EXPLAIN QUERY PLAN '+sql).fetchall()
        rows=c.execute(sql).fetchmany(100001)
        if len(rows)>100000:raise ValueError('row_limit')
        encoded=[json.dumps(r,sort_keys=True,default=str) for r in rows]
        row.update(status='completed',rows=len(rows),
            ordered_sha256=hashlib.sha256(json.dumps(encoded).encode()).hexdigest(),
            multiset_sha256=hashlib.sha256(json.dumps(sorted(encoded)).encode()).hexdigest(),
            plan_sha256=hashlib.sha256(json.dumps(plan).encode()).hexdigest(),
            scan_steps=sum('SCAN ' in r[-1] for r in plan),
            automatic_index_steps=sum('AUTOMATIC' in r[-1] for r in plan))
    except (sqlite3.Error,ValueError) as error:
        row.update(status='deadline' if time.monotonic()-start>config['timeout'] else 'error',error_type=type(error).__name__)
    row.update(seconds=time.monotonic()-start,cpu_seconds=time.process_time()-cpu)
    results.append(row)
c.set_progress_handler(None,0)
print(json.dumps(dict(version=sqlite3.sqlite_version,compile_options=[r[0] for r in c.execute('PRAGMA compile_options')],features=features,results=results)))
'''

QUERIES = [
    'SELECT count(*) FROM events e WHERE e.kind=2 AND EXISTS '
    '(SELECT 1 FROM events p WHERE p.visit=e.visit AND p.kind=1)',
    'SELECT count(*) FROM events e WHERE NOT EXISTS (SELECT 1 FROM items i WHERE i.visit=e.visit)',
    'SELECT kind,count(*),sum(CAST(visit AS INTEGER)) FROM events GROUP BY kind ORDER BY kind',
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before-image', required=True)
    parser.add_argument('--after-image', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--database', type=Path)
    parser.add_argument('--queries', type=Path)
    parser.add_argument('--timeout', type=float, default=30)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if bool(args.database) != bool(args.queries) or not 0 < args.timeout <= 180:
        raise ValueError('External checks require both database and query list, and a bounded timeout')
    queries = json.loads(args.queries.read_text()) if args.queries else QUERIES
    if not isinstance(queries, list) or not 1 <= len(queries) <= 100 or any(
            not isinstance(q, str) or not q.strip() or q.lstrip().split(None, 1)[0].upper() not in {'SELECT','WITH'} for q in queries):
        raise ValueError('Expected 1-100 SELECT/WITH queries')
    if not args.execute:
        print(json.dumps(dict(status='planned',paid_calls=0,queries=len(queries))));return
    args.output.mkdir(parents=True, exist_ok=False)
    database = args.database.resolve(strict=True) if args.database else None
    source_hash = hashlib.sha256(database.read_bytes()).hexdigest() if database else None
    phases = []
    for image in (args.before_image, args.after_image):
        identity = json.loads(subprocess.check_output(['docker','image','inspect',image]))[0]['Id']
        name = 'mas-sqlite-probe-' + uuid.uuid4().hex[:12]
        command = ['docker','run','--rm','--name',name,'--network','none','--cpus','8','--memory','8g','-i']
        if database:command += ['--mount',f'type=bind,src={database},dst=/input.sqlite,readonly']
        command += [identity,'python3','-c',PROBE]
        try:
            result = subprocess.run(command,input=json.dumps(dict(external=bool(database),queries=queries,timeout=args.timeout)),
                text=True,capture_output=True,timeout=len(queries)*args.timeout+60,check=True)
        finally:
            subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=15)
        phases.append(dict(image_id=identity,**json.loads(result.stdout)))
    unchanged = database is None or hashlib.sha256(database.read_bytes()).hexdigest() == source_hash
    comparisons = []
    for before, after in zip(phases[0]['results'], phases[1]['results']):
        complete = before['status'] == after['status'] == 'completed'
        comparisons.append(dict(query_sha256=before['query_sha256'],
            same_rows=(before['multiset_sha256']==after['multiset_sha256']) if complete else None,
            same_order=(before['ordered_sha256']==after['ordered_sha256']) if complete else None,
            before_seconds=before['seconds'],after_seconds=after['seconds']))
    features = all(phases[1]['features'].get(k) for k,v in phases[0]['features'].items() if v)
    passed = unchanged and features and all(r['same_rows'] is True for r in comparisons)
    receipt = dict(passed=passed,paid_calls=0,phases=phases,comparisons=comparisons,
        database_sha256=source_hash,database_unchanged=unchanged,baseline_features_preserved=features,
        scope='Sequential read-only query checks; exact row multiset equality, not full SQL compatibility or model speedup')
    write_json(args.output/'summary.json',receipt)
    print(json.dumps(receipt))
    raise SystemExit(0 if passed else 1)


if __name__ == '__main__':main()
