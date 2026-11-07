from analysis.evidence_usage import merged, duration


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
    from harness.evidence_mas.store import Store
    from harness.evidence_mas.decision import DecisionProtocol
    root=tmp_path/'native-profile/evidence'
    store=Store(root,'benchmark-evidence')
    DecisionProtocol(store).initialize('PRIVATE_TASK_CONTENT')
    store.call('obs.capture',dict(tool_name='Bash',tool_input={'command':'PRIVATE_COMMAND'},
        tool_output='{"answer": 1}',agent_id='worker',status='success',completeness='complete'),role='collector')
    store.call('obs.list',{},role='lead')
    before=hashlib.sha256((root/'store.sqlite').read_bytes()).hexdigest()
    result=workspace(tmp_path,datetime.now(timezone.utc).timestamp()-10,60,
        dict(answer_type='numeric_exact',target=1,scoring_contract={}))
    assert result['lead_worker_preview_observations']==1
    assert result['lead_direct_worker_reads']==0
    assert result['gold_in_final_candidates'] is True
    assert 'PRIVATE' not in json.dumps(result)
    assert hashlib.sha256((root/'store.sqlite').read_bytes()).hexdigest()==before
