"""Offline FDABench scope, reference isolation, assets and scoring contracts."""

import json
import sqlite3
from types import SimpleNamespace

import pytest

from benchmarks.fdabench import tasks, evaluation
from benchmarks._external import asset_manifest
from scripts.common import run, score


def example(**updates):
    row = dict(task_id="FDA0001", instance_id="bird1", db="retail", database_type="bird",
               question_type="single_choice", query="Compute the total", options={"A": "1", "B": "2"},
               correct_answer=["A"], tools_available=["execute_sql"],
               gold_subtasks=[{"expected_SQL": "PRIVATE_GOLD"}], explanation="PRIVATE_GOLD")
    row.update(updates)
    return row


def report(**updates):
    row = example(question_type="report", ground_truth_report="PRIVATE_GOLD", sql_result="1",
        frozen_web_search={"searches": []}, frozen_vector_search={"searches": []},
        rubric=dict(evaluation_dimensions={k: dict(weight=0.25, criteria="PRIVATE_GOLD") for k in tasks.DIMENSIONS},
                    chain_validation=[dict(step=1, tool="execute_sql", rationale="PRIVATE_GOLD")]))
    row.update(updates)
    return row


def load(tmp_path, rows):
    path = tmp_path / "release.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows))
    return tasks.read_catalog(path)


def test_only_local_publicly_scoreable_tasks_enter_pool(tmp_path):
    values, excluded = load(tmp_path, [example(), example(task_id="FDA0002", correct_answer=None),
        example(task_id="FDA0003", database_type="Spider2-lite", instance_id="bq001"),
        example(task_id="FDA0004", database_type="Spider2-lite", instance_id="sf_bq001"),
        example(task_id="FDA0005", database_type="Spider2-lite", instance_id="local001"),
        report(task_id="FDA0006"), report(task_id="FDA0007", ground_truth_report="")])
    assert [t.id for t in values] == ["FDA0001", "FDA0005", "FDA0006"]
    assert [x["reason"] for x in excluded] == ["no_public_answer", "cloud_database_disabled",
                                               "cloud_database_disabled", "missing_report_reference"]
    for task in values:
        assert "PRIVATE_GOLD" not in json.dumps(task.public())
        assert "PRIVATE_GOLD" not in run.instructions(task, "claude-code-subagents", timeout=1800)


@pytest.mark.parametrize("answer", [[], None, "A", ["Z"], ["A", "A"], ["A", "B"], [True]])
def test_invalid_single_choice_reference_excluded(tmp_path, answer):
    values, excluded = load(tmp_path, [example(correct_answer=answer)])
    assert not values and len(excluded) == 1


def test_repeated_instance_ids_are_not_task_ids(tmp_path):
    values, _ = load(tmp_path, [example(), example(task_id="FDA0002")])
    assert len(values) == 2
    with pytest.raises(ValueError, match="Duplicate"):
        load(tmp_path, [example(), example()])


def test_reference_change_changes_task_binding(tmp_path):
    first = load(tmp_path, [example()])[0][0]
    second = load(tmp_path, [example(correct_answer=["B"])])[0][0]
    assert first.question == second.question
    assert first.source_sha256 != second.source_sha256


def test_mounts_only_selected_sqlite_and_verified_raw_corpus(tmp_path):
    task = load(tmp_path, [example()])[0][0]
    data = tmp_path / "data"
    path = tasks.database_path(task, data)
    path.parent.mkdir(parents=True)
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE example (x INTEGER)")
    assert tasks.mounts(task, data) == [(path, "/data/database.sqlite", True)]
    corpus_task = load(tmp_path, [example(tools_available=["execute_sql", "vector_search"])])[0][0]
    with pytest.raises(ValueError, match="corpus receipt"):
        tasks.mounts(corpus_task, data)
    corpus = data / "corpus"
    corpus.mkdir()
    (corpus / "paper.txt").write_text("Public raw document")
    (data / "corpus-receipt.json").write_text(json.dumps(dict(kind="fdabench-raw-corpus-v1", files=asset_manifest(corpus))))
    from scripts.fdabench.index_corpus import main
    main(["--data", str(data), "--execute"])
    assert len(tasks.mounts(corpus_task, data)) == 3
    (corpus / "paper.txt").write_text("Changed document")
    with pytest.raises(ValueError, match="differs"):
        tasks.mounts(corpus_task, data)


@pytest.mark.parametrize("response,expected", [(' ["A"] ', 1), ('["B"]', 0), ('A', 0),
    ('["A","A"]', 0), ('["A","B"]', 0), ('["A","Z"]', 0), ('{"answer":"A"}', 0), ('', 0)])
def test_choice_exact_match(response, expected):
    assert evaluation.choice_score(dict(response=response, reference=example(), question_type="single_choice")) == expected


def test_multiple_choice_is_set_equality_not_partial_credit():
    row = dict(response='["B","A"]', reference=example(correct_answer=["A", "B"]), question_type="multiple_choice")
    assert evaluation.choice_score(row) == 1
    row["response"] = '["A"]'
    assert evaluation.choice_score(row) == 0


def test_report_scores_strict_and_weighted():
    row = dict(response="Generated report", reference=report(), question_type="report")
    values = {k: 0.5 for k in tasks.DIMENSIONS}
    values["SQL_ACCURACY"] = 1
    assert evaluation.report_score(row, {"scores": values}) == 0.625
    values["SQL_ACCURACY"] = 0.5
    with pytest.raises(ValueError):
        evaluation.report_score(row, {"scores": values})
    with pytest.raises(ValueError):
        evaluation.report_score(row, {"scores": {}})


def test_choices_never_call_judge_and_failed_report_is_unknown(tmp_path):
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("fixture provider failure")
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    rows = [dict(task_id="FDA0001", question_type="single_choice", response='["A"]', reference=example()),
            dict(task_id="FDA0002", question_type="report", response="Answer", reference=report()),
            dict(task_id="FDA0003", question_type="report", response="Later", reference=report())]
    values = score.judge_rows(rows, benchmark="fdabench", upstream=tmp_path, model="fake",
                              output=tmp_path, client=client)
    assert [v["score"] for v in values] == [1, None, None]
    assert len(calls) == 1
    assert values[1]["status"] == "judge_error" and values[2]["status"] == "not_started"


def test_preparation_is_plan_only(tmp_path, monkeypatch, capsys):
    from scripts.fdabench import prepare
    monkeypatch.setattr(prepare, "inventory", lambda *a: pytest.fail("Planning made a network request"))
    root = tmp_path / "external"
    assert prepare.main(["--root", str(root)]) == 0
    assert not root.exists() and '"paid_calls": 0' in capsys.readouterr().out


def test_local_document_search_is_read_only_and_bounded(tmp_path):
    from harness.runtime_support.documents import build, search
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "facts.txt").write_text("Regional sales increased in the northern district.")
    index = tmp_path / "index.sqlite"
    result = build(corpus, index)
    assert result["chunks"] == 1 and result["paid_calls"] == 0
    assert search(index, "regional")[0]["path"] == "/corpus/facts.txt"
    assert search(index, "nonexistent") == []
    with pytest.raises(ValueError):
        search(index, "regional", limit=10000)


def test_matrix_opt_in_preserves_existing_default_and_fda_paths(tmp_path):
    from scripts.studies import benchmark_matrix as matrix
    from scripts.common.grading import needs_judge
    assert 'fdabench' not in matrix.BENCHMARKS
    assert 'fdabench' in matrix.SUPPORTED_BENCHMARKS
    task = load(tmp_path, [example()])[0][0]
    args = SimpleNamespace(root=tmp_path, image='existing', credentials=tmp_path/'key',
                           proofs=tmp_path/'proofs', output=tmp_path/'batch')
    command = matrix.solver_command(args, 'fdabench', task, 'claude-code-single-agent', tmp_path/'run')
    assert command[command.index('--data') + 1] == str(tmp_path/'fdabench/data')
    assert command[command.index('--tasks') + 1] == str(tmp_path/'fdabench/release')
    assert not needs_judge('fdabench', task, tmp_path/'run', True)


def test_asset_download_hash_failure_never_accepts_file(tmp_path, monkeypatch):
    from scripts.fdabench import prepare
    def bad(url, destination, size):
        destination.write_bytes(b"bad")
    monkeypatch.setattr(prepare, "download_blob", bad)
    item = dict(path="data.sqlite", size=3, lfs={"oid":"0" * 64})
    target = tmp_path/'data.sqlite'
    with pytest.raises(ValueError, match="integrity"):
        prepare.fetch('fixture', 'pin', item, target)
    assert not target.exists()


def test_asset_ranges_validate_content_range(tmp_path, monkeypatch):
    from scripts.fdabench import prepare
    class Result:
        def getheader(self, name):
            return "bytes 0-1/2"
    monkeypatch.setattr(prepare, 'response', lambda *a, **kw: (SimpleNamespace(close=lambda: None), Result()))
    with pytest.raises(ValueError, match="different byte range"):
        prepare.download_blob('https://fixture', tmp_path/'download', 65 * 1024 * 1024)
    assert not (tmp_path/'download').exists()


def test_background_preparation_is_plan_only(tmp_path, monkeypatch):
    from scripts.fdabench import prepare_all
    monkeypatch.setattr(prepare_all.subprocess, 'run', lambda *a, **kw: pytest.fail('Planning started subprocess'))
    assert prepare_all.main(['--root', str(tmp_path/'data'), '--output', str(tmp_path/'receipt')]) == 0
    assert not (tmp_path/'receipt').exists()


def test_pinned_release_rejects_modified_input(tmp_path):
    for name in tasks.RELEASE_SHA256:
        (tmp_path / name).write_text(json.dumps(example()))
    with pytest.raises(ValueError, match='content differs'):
        tasks.read_catalog(tmp_path)


def test_asset_network_retries_are_bounded_and_integrity_errors_are_not_retried(monkeypatch):
    from scripts.fdabench import prepare
    waits = []
    monkeypatch.setattr(prepare.time, 'sleep', waits.append)
    calls = []
    @prepare.retry_transfer
    def broken():
        calls.append(1)
        raise BrokenPipeError('fixture')
    with pytest.raises(BrokenPipeError):
        broken()
    assert len(calls) == 5 and waits == [2, 4, 8, 16]
    @prepare.retry_transfer
    def invalid():
        raise ValueError('integrity')
    with pytest.raises(ValueError):
        invalid()
    assert waits == [2, 4, 8, 16]


def test_spider1_uses_upstream_test_database_not_equal_named_train_database(tmp_path):
    import zipfile
    from scripts.fdabench.prepare import extract_databases
    task = load(tmp_path, [example(database_type='spider1')])[0][0]
    archive = tmp_path/'databases.zip'
    with zipfile.ZipFile(archive, 'w') as bundle:
        bundle.writestr('spider_data/database/retail/retail.sqlite', b'train')
        bundle.writestr('spider_data/test_database/retail/retail.sqlite', b'test')
    extract_databases(archive, [task], tmp_path/'data', 'spider1')
    assert tasks.database_path(task, tmp_path/'data').read_bytes() == b'test'


def test_hf_token_is_scoped_to_gated_corpus_and_never_forwarded_to_cdn(monkeypatch):
    from scripts.fdabench import prepare
    monkeypatch.setattr(prepare, 'HF_TOKEN', 'fake-test-token')
    target = '/datasets/' + prepare.CORPUS[0] + '/resolve/pin/image.png'
    for host in ('huggingface.co', 'hf-mirror.com'):
        assert prepare.auth_headers(host, target) == {'Authorization': 'Bearer fake-test-token'}
        assert prepare.auth_headers(host, '/api/datasets/' + prepare.CORPUS[0] + '/tree/pin')
        assert prepare.auth_headers(host, '/datasets/public/data/resolve/pin/file') == {}
        assert prepare.auth_headers(host, target.replace('FDABench-File/', 'FDABench-File-other/')) == {}
    for host in ('cdn-lfs.huggingface.co', 'cas-bridge.xethub.hf.co', 'cdn-lfs.hf-mirror.com', 'example.com'):
        assert prepare.auth_headers(host, target) == {}


def test_bulk_download_dns_checks_expire_and_fail_closed(monkeypatch):
    from scripts.fdabench import prepare
    calls = []
    clock = [0]
    monkeypatch.setattr(prepare, 'DNS_CHECKS', {})
    monkeypatch.setattr(prepare.time, 'monotonic', lambda: clock[0])
    def resolve(*args, **kwargs):
        calls.append(args)
        return [(None, None, None, None, ('8.8.8.8', 443))]
    monkeypatch.setattr(prepare.socket, 'getaddrinfo', resolve)
    prepare.validate_download_host('huggingface.co')
    prepare.validate_download_host('huggingface.co')
    assert len(calls) == 1
    clock[0] = 121
    prepare.validate_download_host('huggingface.co')
    assert len(calls) == 2
    monkeypatch.setattr(prepare.socket, 'getaddrinfo', lambda *a, **kw:
                        [(None, None, None, None, ('127.0.0.1', 443))])
    with pytest.raises(ValueError, match='non-public'):
        prepare.validate_download_host('hf-mirror.com')


def test_mirror_response_is_direct_https_and_strips_redirect_auth(monkeypatch):
    from scripts.fdabench import prepare
    monkeypatch.setattr(prepare, 'HF_TOKEN', 'fake-test-token')
    monkeypatch.setattr(prepare, 'validate_download_host', lambda host: None)
    requests, closed = [], []
    class Connection:
        def __init__(self, host, port, timeout):
            self.host = host
            assert port == 443 and timeout == prepare.ASSET_TIMEOUT
        def request(self, method, target, headers):
            requests.append((self.host, method, target, headers))
        def getresponse(self):
            redirect = self.host == 'hf-mirror.com'
            return SimpleNamespace(status=302 if redirect else 206,
                getheader=lambda name, default='': 'https://cdn-lfs.hf-mirror.com/file?signature=fixture')
        def close(self):
            closed.append(self.host)
    monkeypatch.setattr(prepare.http.client, 'HTTPSConnection', Connection)
    url = prepare.HF_ENDPOINT + '/datasets/' + prepare.CORPUS[0] + '/resolve/pin/image.png'
    connection, result = prepare.response(url, byte_range=(0, 9))
    assert result.status == 206 and closed == ['hf-mirror.com']
    assert requests[0][3]['Authorization'] == 'Bearer fake-test-token'
    assert 'Authorization' not in requests[1][3]
    assert all(row[3]['Range'] == 'bytes=0-9' for row in requests)
    connection.close()


@pytest.mark.parametrize('url', ['http://hf-mirror.com/file', 'https://hf-mirror.com.evil.test/file',
                                'https://evil.test/file', 'https://user@hf-mirror.com/file',
                                'https://hf-mirror.com:444/file'])
def test_mirror_rejects_unsafe_download_hosts(url, monkeypatch):
    from scripts.fdabench import prepare
    monkeypatch.setattr(prepare, 'validate_download_host', lambda host: pytest.fail('Unsafe URL reached DNS'))
    with pytest.raises(ValueError):
        prepare.response(url)


def test_mirror_defaults_and_background_endpoint_propagation(tmp_path, monkeypatch, capsys):
    from scripts.fdabench import prepare, prepare_all
    prepare.main(['--root', str(tmp_path/'data')])
    assert json.loads(capsys.readouterr().out)['endpoint'] == 'https://hf-mirror.com'
    commands = []
    def run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=1)
    monkeypatch.setattr(prepare_all.subprocess, 'run', run)
    assert prepare_all.main(['--root', str(tmp_path/'data'), '--output', str(tmp_path/'receipt'), '--execute']) == 1
    assert commands[0][commands[0].index('--hf-endpoint') + 1] == 'https://hf-mirror.com'
    state = json.loads((tmp_path/'receipt/status.json').read_text())
    assert state['transport'] == 'server-direct-https' and state['endpoint'] == 'https://hf-mirror.com'


def test_mirror_reuses_verified_file_without_download(tmp_path, monkeypatch):
    import hashlib
    from scripts.fdabench import prepare
    target = tmp_path/'complete'
    target.write_bytes(b'complete')
    item = dict(path='complete', size=8, lfs=dict(oid=hashlib.sha256(b'complete').hexdigest()))
    monkeypatch.setattr(prepare, 'download_blob', lambda *a: pytest.fail('Redownloaded complete file'))
    receipt = prepare.fetch('fixture', 'pin', item, target)
    assert receipt['endpoint'] == 'https://hf-mirror.com'


def test_mirror_reuses_complete_range_chunks(tmp_path, monkeypatch):
    from scripts.fdabench import prepare
    target = tmp_path/'archive.part'
    parts = tmp_path/'archive.part.ranges'
    parts.mkdir()
    size, chunk = 64 * 1024 * 1024, 16 * 1024 * 1024
    for start in range(0, size, chunk):
        with (parts/str(start)).open('wb') as stream:
            stream.truncate(chunk)
    monkeypatch.setattr(prepare, 'response', lambda *a, **kw: pytest.fail('Redownloaded complete range'))
    prepare.download_blob('https://hf-mirror.com/archive', target, size)
    assert target.stat().st_size == size


def test_mirror_auth_failure_has_no_retry_or_official_fallback(monkeypatch):
    from scripts.fdabench import prepare
    calls = []
    monkeypatch.setattr(prepare, 'validate_download_host', lambda host: None)
    class Connection:
        def __init__(self, host, *a, **kw):
            calls.append(host)
        def request(self, *a, **kw):
            pass
        def getresponse(self):
            return SimpleNamespace(status=401)
        def close(self):
            pass
    monkeypatch.setattr(prepare.http.client, 'HTTPSConnection', Connection)
    with pytest.raises(RuntimeError, match='HTTP 401'):
        prepare.inventory(*prepare.CORPUS)
    assert calls == ['hf-mirror.com']


def test_partial_small_asset_resumes_exact_range(tmp_path, monkeypatch):
    import io
    from scripts.fdabench import prepare
    target = tmp_path/'asset.part'
    target.write_bytes(b'abc')
    ranges = []
    class Result(io.BytesIO):
        def getheader(self, name):
            return 'bytes 3-5/6'
    def response(*args, byte_range=None):
        ranges.append(byte_range)
        return SimpleNamespace(close=lambda: None), Result(b'def')
    monkeypatch.setattr(prepare, 'response', response)
    prepare.download_blob('https://hf-mirror.com/file', target, 6)
    assert ranges == [(3, 5)] and target.read_bytes() == b'abcdef'


def test_partial_resume_rejects_wrong_range_without_append(tmp_path, monkeypatch):
    import io
    from scripts.fdabench import prepare
    target = tmp_path/'asset.part'
    target.write_bytes(b'abc')
    class Result(io.BytesIO):
        def getheader(self, name):
            return 'bytes 0-5/6'
    monkeypatch.setattr(prepare, 'response', lambda *a, **kw:
                        (SimpleNamespace(close=lambda: None), Result(b'abcdef')))
    with pytest.raises(ValueError, match='different byte range'):
        prepare.download_blob('https://hf-mirror.com/file', target, 6)
    assert target.read_bytes() == b'abc'


def test_failed_small_transfer_retains_bytes_and_resumes_on_bounded_retry(tmp_path, monkeypatch):
    import io
    from scripts.fdabench import prepare
    target = tmp_path/'asset.part'
    calls = []
    class Interrupted:
        def __init__(self):
            self.sent = False
        def read1(self, size):
            if self.sent:
                raise BrokenPipeError('fixture')
            self.sent = True
            return b'abc'
    class Remaining(io.BytesIO):
        def getheader(self, name):
            return 'bytes 3-5/6'
    def response(*a, byte_range=None):
        calls.append(byte_range)
        result = Interrupted() if byte_range is None else Remaining(b'def')
        return SimpleNamespace(close=lambda: None), result
    monkeypatch.setattr(prepare, 'response', response)
    monkeypatch.setattr(prepare.time, 'sleep', lambda _: None)
    prepare.download_blob('https://hf-mirror.com/file', target, 6)
    assert calls == [None, (3, 5)] and target.read_bytes() == b'abcdef'


def test_connection_pool_reuses_only_consumed_responses(monkeypatch):
    import threading
    from scripts.fdabench import prepare
    monkeypatch.setattr(prepare, 'CONNECTIONS', threading.local())
    created, closed = [], []
    class Connection:
        def __init__(self, host, *args, **kwargs):
            created.append(self)
        def getresponse(self):
            return SimpleNamespace(isclosed=lambda: True, will_close=False, length=0)
        def close(self):
            closed.append(self)
    monkeypatch.setattr(prepare.http.client, 'HTTPSConnection', Connection)
    first = prepare.ConnectionLease('hf-mirror.com')
    first.getresponse()
    first.close()
    second = prepare.ConnectionLease('hf-mirror.com')
    assert len(created) == 1 and not closed
    second.close()
    assert len(closed) == 1
    third = prepare.ConnectionLease('hf-mirror.com')
    third.getresponse()
    third.close(discard=True)
    assert len(created) == len(closed) == 2


def test_parallel_progress_is_completion_order_not_submission_order():
    import threading
    from scripts.fdabench import prepare
    release = threading.Event()
    def operation(item):
        if item == 'slow':
            assert release.wait(5)
        return item
    results = prepare.parallel_items(operation, ['slow', 'fast'], 2)
    try:
        assert next(results) == 'fast'
    finally:
        release.set()
    assert list(results) == ['slow']


def test_background_termination_records_interrupted(tmp_path, monkeypatch):
    import signal
    from scripts.fdabench import prepare_all
    previous = signal.getsignal(signal.SIGTERM)
    def run(*args, **kwargs):
        prepare_all.interrupted(signal.SIGTERM, None)
    monkeypatch.setattr(prepare_all.subprocess, 'run', run)
    output = tmp_path/'receipt'
    assert prepare_all.main(['--root', str(tmp_path/'data'), '--output', str(output), '--execute']) == 143
    state = json.loads((output/'status.json').read_text())
    assert state['status'] == 'interrupted' and state['signal'] == signal.SIGTERM
    assert signal.getsignal(signal.SIGTERM) == previous


def test_opt_in_cdn_proxy_never_routes_mirror_or_receives_credentials(tmp_path, monkeypatch):
    import threading
    from scripts.fdabench import prepare
    monkeypatch.setattr(prepare, 'CONNECTIONS', threading.local())
    monkeypatch.setattr(prepare, 'CDN_PROXY_SOCKET', tmp_path/'clash.sock')
    direct, proxied, tunnels = [], [], []
    class Connection:
        def __init__(self, host, *args, **kwargs):
            direct.append(host)
        def set_tunnel(self, host, port):
            tunnels.append((host, port))
        def close(self):
            pass
    def proxy(host, port, secure, timeout, path):
        proxied.append(host)
        assert path == tmp_path/'clash.sock' and secure
        return Connection.__new__(Connection)
    monkeypatch.setattr(prepare.http.client, 'HTTPSConnection', Connection)
    monkeypatch.setattr(prepare, 'proxy_connection', proxy)
    for host in ('hf-mirror.com', 'huggingface.co', 'us.aws.cdn.hf.co'):
        prepare.ConnectionLease(host).close()
    assert direct == ['hf-mirror.com', 'huggingface.co']
    assert proxied == ['us.aws.cdn.hf.co'] and tunnels == [('us.aws.cdn.hf.co', 443)]
    assert prepare.auth_headers('us.aws.cdn.hf.co', '/datasets/' + prepare.CORPUS[0] + '/file') == {}
    monkeypatch.setattr(prepare, 'CDN_PROXY_SOCKET', None)
    assert not prepare.use_cdn_proxy('us.aws.cdn.hf.co')


def test_background_propagates_explicit_cdn_proxy(tmp_path, monkeypatch):
    from scripts.fdabench import prepare_all
    commands = []
    def run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=1)
    monkeypatch.setattr(prepare_all.subprocess, 'run', run)
    output, proxy = tmp_path/'receipt', tmp_path/'clash.sock'
    assert prepare_all.main(['--root', str(tmp_path/'data'), '--output', str(output),
                             '--cdn-proxy-socket', str(proxy), '--execute']) == 1
    assert commands[0][commands[0].index('--cdn-proxy-socket') + 1] == str(proxy)
    assert json.loads((output/'status.json').read_text())['transport'] == 'mirror-direct-cdn-mac-clash'


def test_asset_connect_skips_unreachable_addresses_and_prefers_recent_success(monkeypatch):
    from scripts.fdabench import prepare
    monkeypatch.setattr(prepare, 'WORKING_ADDRESSES', {})
    monkeypatch.setattr(prepare.socket, 'getaddrinfo', lambda *a, **kw:
                        [(None, None, None, None, (ip, 443)) for ip in ('8.8.8.8', '1.1.1.1')])
    calls, timeouts = [], []
    def connect(address, *, timeout, source_address):
        calls.append((address, timeout))
        if address[0] == '8.8.8.8':
            raise TimeoutError('fixture')
        return SimpleNamespace(settimeout=timeouts.append)
    monkeypatch.setattr(prepare.socket, 'create_connection', connect)
    prepare.asset_socket(('us.aws.cdn.hf.co', 443))
    prepare.asset_socket(('us.aws.cdn.hf.co', 443))
    assert [a[0][0] for a in calls] == ['8.8.8.8', '1.1.1.1', '1.1.1.1']
    assert all(a[1] <= 2 for a in calls) and timeouts == [20, 20]


def test_asset_address_list_has_one_total_deadline(monkeypatch):
    from scripts.fdabench import prepare
    monkeypatch.setattr(prepare, 'WORKING_ADDRESSES', {})
    monkeypatch.setattr(prepare.socket, 'getaddrinfo', lambda *a, **kw:
                        [(None, None, None, None, (f'8.8.8.{i}', 443)) for i in range(1, 11)])
    clock, calls = [0], []
    monkeypatch.setattr(prepare.time, 'monotonic', lambda: clock[0])
    def connect(address, *, timeout, source_address):
        calls.append(address)
        clock[0] += timeout
        raise TimeoutError('fixture')
    monkeypatch.setattr(prepare.socket, 'create_connection', connect)
    with pytest.raises(TimeoutError, match='address-list'):
        prepare.asset_socket(('us.aws.cdn.hf.co', 443), timeout=3)
    assert clock[0] == 3 and len(calls) == 2
