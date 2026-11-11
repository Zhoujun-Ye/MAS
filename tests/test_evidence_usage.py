from analysis.timing import merged, duration


def test_overlapping_agent_intervals_are_not_added_as_wall_time():
    assert merged([(0,3),(1,2),(3,5),(8,9)]) == [(0,5),(8,9)]
    assert duration([(0,3),(1,4)]) == 4


def test_empty_and_invalid_intervals_do_not_invent_busy_time():
    assert duration([]) == 0
    assert duration([(3,2),(1,1)]) == 0


def test_workspace_audit_is_readonly_and_never_exports_blob_payloads(tmp_path):
    import hashlib
    import json
    from datetime import datetime, timezone
    from analysis.evidence_usage import workspace
    import sqlite3
    root=tmp_path/'native-profile/evidence'
    (root/'blobs').mkdir(parents=True)
    def blob(value):
        data=json.dumps(value).encode()
        key=hashlib.sha256(data).hexdigest()
        (root/'blobs'/key).write_bytes(data)
        return key
    with sqlite3.connect(root/'store.sqlite') as db:
        db.executescript('CREATE TABLE meta(key TEXT,value TEXT); CREATE TABLE objects(id TEXT, revision INTEGER, kind TEXT, body TEXT); CREATE TABLE events(seq INTEGER PRIMARY KEY,body TEXT);')
        db.execute('INSERT INTO meta VALUES(?,?)',('run_id','benchmark-evidence'))
        db.execute('INSERT INTO objects VALUES(?,?,?,?)',('obs',1,'observation',json.dumps(dict(id='obs',agent_id='worker'))))
        for index,(method,result) in enumerate((('obs.list',dict(items=[dict(id='obs',preview='PRIVATE_COMMAND')])),
                ('decision.view',dict(protocol='decision-v4',snapshot='s',counts=dict(candidates=1),
                    candidates=[dict(id='candidate',value=1)],intermediate=[])))):
            event=dict(method=method,role='lead',timestamp=datetime.now(timezone.utc).isoformat(),
                arguments_ref=blob({}),result_ref=blob(result))
            db.execute('INSERT INTO events VALUES(?,?)',(index,json.dumps(event)))
    before=hashlib.sha256((root/'store.sqlite').read_bytes()).hexdigest()
    result=workspace(tmp_path,datetime.now(timezone.utc).timestamp()-10,60,
        dict(answer_type='numeric_exact',target=1,scoring_contract={}))
    assert result['lead_worker_preview_observations']==1
    assert result['lead_direct_worker_reads']==0
    assert result['gold_in_final_candidates'] is None
    assert result['gold_in_recorded_candidates'] is True
    assert result['recorded_candidates_complete'] is True
    assert 'PRIVATE' not in json.dumps(result)
    assert hashlib.sha256((root/'store.sqlite').read_bytes()).hexdigest()==before


def test_historical_reader_never_creates_missing_store(tmp_path):
    import pytest
    from analysis.historical_workspace import WorkspaceReader
    with pytest.raises(ValueError,match='Missing regular'):
        WorkspaceReader(tmp_path/'missing')
    assert not (tmp_path/'missing').exists()
