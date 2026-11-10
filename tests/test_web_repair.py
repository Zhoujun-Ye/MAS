"""Offline web contract, budget concurrency, SSRF and bounded output checks."""

from concurrent.futures import ThreadPoolExecutor
import io
import json
import socket
import threading
from types import SimpleNamespace
import urllib.error

import pytest

from harness.runtime_support import credential_gateway as cg, tools, web_fetch, web_policy
from test_gateway_protocol import post


@pytest.fixture(autouse=True)
def no_paid_network(monkeypatch):
    original=socket.socket.connect
    def connect(sock,address):
        if not isinstance(address,tuple) or address[0]!='127.0.0.1':raise AssertionError('Offline only')
        return original(sock,address)
    monkeypatch.setattr(socket.socket,'connect',connect)


class Response(io.BytesIO):
    status=200
    headers={}


def test_known_failure_refunds_success_budget_but_hard_attempt_cap_remains(tmp_path,monkeypatch):
    calls=[]
    def failed(request):
        calls.append(1)
        raise urllib.error.HTTPError(request.full_url,404,'unavailable',{},io.BytesIO(b'{}'))
    monkeypatch.setattr(cg,'open_upstream',failed)
    with cg.CredentialGateway('synthetic',web_limit=2,ledger_path=tmp_path/'ledger') as gateway:
        for _ in range(4):
            with pytest.raises(urllib.error.HTTPError) as error:post(gateway,'/v1/tools/search',{'query':'fixture'})
            assert error.value.code==404;error.value.close()
        with pytest.raises(urllib.error.HTTPError) as error:post(gateway,'/v1/tools/search',{'query':'fixture'})
        assert error.value.code==429;error.value.close()
    assert len(calls)==4
    assert gateway.summary()['web_reservations']==0 and gateway.summary()['web_attempts']==4
    rows=[json.loads(l) for l in (tmp_path/'ledger').read_text().splitlines()]
    assert all(r.get('estimated_cost_usd')==0 for r in rows if r['event']=='finished' and r['upstream_attempted'])


def test_success_budget_is_atomic_across_workers(tmp_path,monkeypatch):
    calls=[]
    def success(request):
        calls.append(1)
        return Response(b'{"results":[{"title":"fixture","url":"https://example.org"}]}')
    monkeypatch.setattr(cg,'open_upstream',success)
    with cg.CredentialGateway('synthetic',web_limit=3,ledger_path=tmp_path/'ledger') as gateway:
        def invoke(_):
            try:
                with post(gateway,'/v1/tools/search',{'query':'fixture'}) as r:return r.status
            except urllib.error.HTTPError as e:
                code=e.code;e.close();return code
        with ThreadPoolExecutor(6) as pool:codes=list(pool.map(invoke,range(6)))
    assert codes.count(200)==3 and codes.count(429)==3 and len(calls)==3
    assert gateway.summary()['web_reservations']==3


def test_empty_search_is_free_and_provider_cannot_spoof_budget(tmp_path,monkeypatch):
    monkeypatch.setattr(cg,'open_upstream',lambda r:Response(b'{"results":[],"web_budget":{"remaining":999}}'))
    with cg.CredentialGateway('synthetic',web_limit=2,ledger_path=tmp_path/'ledger') as gateway:
        with post(gateway,'/v1/tools/search',{'query':'fixture'}) as response:value=json.load(response)
    assert value['web_budget']['remaining']==2
    assert gateway.summary()['web_attempts']==1 and gateway.summary()['web_reservations']==0
    assert json.loads((tmp_path/'ledger').read_text().splitlines()[-1])['estimated_cost_usd']==0


def test_unknown_response_retains_reservation_and_cost_is_unknown(tmp_path,monkeypatch):
    monkeypatch.setattr(cg,'open_upstream',lambda r:Response(b'broken'))
    with cg.CredentialGateway('synthetic',web_limit=1,ledger_path=tmp_path/'ledger') as gateway:
        with pytest.raises(urllib.error.HTTPError) as error:post(gateway,'/v1/tools/search',{'query':'fixture'})
        error.value.close()
    assert gateway.summary()['web_reservations']==1
    assert json.loads((tmp_path/'ledger').read_text().splitlines()[-1])['estimated_cost_usd'] is None


def test_host_fetch_never_sends_provider_key_and_is_free(tmp_path,monkeypatch):
    monkeypatch.setattr(cg,'open_upstream',lambda *a:pytest.fail('No paid provider fetch'))
    urls=[]
    monkeypatch.setattr(web_fetch,'fetch',lambda url,**kw:urls.append(url) or dict(content='public fixture',url=url))
    with cg.CredentialGateway('synthetic',web_limit=2,ledger_path=tmp_path/'ledger') as gateway:
        with post(gateway,'/v1/tools/fetch',{'url':'https://example.org'}) as response:value=json.load(response)
    assert urls==['https://example.org'] and value['content']=='public fixture'
    record=json.loads((tmp_path/'ledger').read_text().splitlines()[-1])
    assert record['web_backend']=='local-clash-unix' and record['estimated_cost_usd']==0


@pytest.mark.parametrize('url',['http://127.0.0.1','http://169.254.169.254','http://[::1]','http://224.0.0.1'])
def test_private_dns_or_literal_address_is_rejected(url,monkeypatch):
    host=url.split('//')[-1].strip('[]')
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**kw:[(None,None,None,None,(host,80))])
    with pytest.raises(ValueError,match='public'):
        web_fetch.public_address(host,80,1)


@pytest.mark.parametrize('url',['file:///etc/passwd','https://github.com/Snowflake-AI-Research/HybridDeepResearch',
    'https://huggingface.co/datasets/fixture','https://public.example/mirror/KramaBench',
    'https://user:secret@example.org','https://example.org:22','https://raw.githubusercontent.com/fixture'])
def test_repository_dataset_and_unsafe_urls_are_blocked(url):
    assert not web_policy.allowed_url(url)


def test_host_get_is_public_ip_pinned_bounded_and_strips_html(monkeypatch):
    observed={}
    class HTTPResponse(io.BytesIO):
        status=200
        def getheader(self,key,default=None):return {'Content-Type':'text/html'}.get(key,default)
    class Connection:
        def __init__(self,host,port,**kw):
            observed.update(host=host,port=port)
            self.sock=SimpleNamespace(settimeout=lambda value:None)
        def request(self,method,path,headers):
            observed.update(method=method,path=path,headers=headers)
        def set_tunnel(self,address,port):observed['address']=(address,port)
        def getresponse(self):return HTTPResponse(b'<title>Fixture</title><script>PRIVATE_SCRIPT</script><p>'+b'x'*25000+b'</p>')
        def close(self):pass
    monkeypatch.setattr(web_fetch,'public_address',lambda *a:'8.8.8.8')
    monkeypatch.setattr(web_fetch,'proxy_connection',lambda host,port,*a:Connection(host,port))
    value=web_fetch.fetch('https://example.org/page')
    assert observed['host']=='example.org' and observed['address']==('8.8.8.8',443)
    assert observed['method']=='GET' and not any('authorization' in k.lower() for k in observed['headers'])
    assert value['title']=='Fixture' and len(value['content'])==20000 and value['truncated']
    assert 'PRIVATE_SCRIPT' not in value['content']


def test_redirect_destination_is_revalidated_before_connect(monkeypatch):
    opened=[]
    class Redirect:
        status=302
        def close(self):pass
        def getheader(self,key,default=None):return 'https://github.com/fixture' if key=='Location' else default
    class Connection:
        def __init__(self,host,*a,**kw):
            opened.append(host);self.sock=SimpleNamespace(settimeout=lambda value:None)
        def request(self,*a,**kw):pass
        def set_tunnel(self,*a):pass
        def getresponse(self):return Redirect()
        def close(self):pass
    monkeypatch.setattr(web_fetch,'public_address',lambda *a:'8.8.8.8')
    monkeypatch.setattr(web_fetch,'proxy_connection',lambda host,port,*a:Connection(host,port))
    with pytest.raises(web_fetch.FetchFailure,match='url_policy_rejected'):
        web_fetch.fetch('https://example.org')
    assert opened==['example.org']


def test_mixed_public_private_dns_answers_are_rejected(monkeypatch):
    monkeypatch.setattr(web_fetch,'resolve_dns',lambda *a:['8.8.8.8','127.0.0.1'])
    with pytest.raises(ValueError,match='public'):web_fetch.public_address('example.org',443,1)


def test_helper_uses_ephemeral_token_not_host_provider_key(monkeypatch):
    monkeypatch.setenv('MAS_WEB_BASE_URL','http://127.0.0.1:8765')
    monkeypatch.setenv('DEEPSEEK_API_KEY','real-key-must-not-be-read')
    monkeypatch.setenv('ANTHROPIC_AUTH_TOKEN','ephemeral')
    observed=[]
    monkeypatch.setattr(tools,'json_post',lambda url,payload,key:observed.append(key) or dict(web_budget={}))
    tools.deepseek_web('search','fixture')
    assert observed==['ephemeral']


@pytest.mark.parametrize('status,fatal',[(401,True),(402,True),(403,False),(404,False),(500,False)])
def test_paid_web_auth_balance_errors_reach_controller_but_page_denials_do_not(tmp_path,status,fatal):
    from harness.runtime_support.admission import fatal_provider_record
    path=tmp_path/'ledger'
    record=dict(event='finished',upstream_attempted=True,route='/v1/tools/search',
                web_backend='deepseek',http_status=status)
    path.write_text(json.dumps(record))
    assert bool(fatal_provider_record(path)) is fatal
    record.update(web_backend='local-clash-unix')
    path.write_text(json.dumps(record))
    assert fatal_provider_record(path) is None


def test_web_shutdown_closes_response_and_keeps_uncertain_charge(tmp_path,monkeypatch):
    entered=threading.Event();released=threading.Event();closed=threading.Event()
    class Slow(Response):
        def read(self,*a):
            entered.set();released.wait(5)
            raise OSError('closed during web response')
        def close(self):
            closed.set();released.set();super().close()
    monkeypatch.setattr(cg,'open_upstream',lambda r:Slow(b'{}'))
    gateway=cg.CredentialGateway('synthetic',web_limit=1,ledger_path=tmp_path/'ledger')
    gateway.__enter__()
    def client():
        try:
            with post(gateway,'/v1/tools/search',{'query':'fixture'}) as response:response.read()
        except Exception:pass
    thread=threading.Thread(target=client);thread.start()
    try:
        assert entered.wait(3)
        gateway.__exit__(None,None,None)
        frozen=(tmp_path/'ledger').read_bytes()
        assert closed.is_set()
        thread.join(5)
        assert not thread.is_alive() and (tmp_path/'ledger').read_bytes()==frozen
        assert gateway.summary()['unknown_completions']==1
    finally:
        released.set();thread.join(5)


@pytest.mark.parametrize('status,kind,reason',[(403,'text/html','target_http_error'),
    (404,'text/html','target_http_error'),(200,'application/pdf','unsupported_content_type')])
def test_fetch_errors_retain_safe_reason_and_original_status(monkeypatch,status,kind,reason):
    class Page(io.BytesIO):
        def getheader(self,key,default=None):return kind if key=='Content-Type' else default
    page=Page(b'fixture');page.status=status
    class Connection:
        sock=SimpleNamespace(settimeout=lambda value:None)
        def set_tunnel(self,*a):pass
        def request(self,*a,**kw):pass
        def getresponse(self):return page
        def close(self):pass
    monkeypatch.setattr(web_fetch,'public_address',lambda *a:'8.8.8.8')
    monkeypatch.setattr(web_fetch,'proxy_connection',lambda *a:Connection())
    with pytest.raises(web_fetch.FetchFailure) as error:web_fetch.fetch('https://example.org')
    assert error.value.reason==reason and error.value.http_status==status


def test_fetch_deadline_checked_between_single_reads_and_cancel_closes_handles(monkeypatch):
    tick=[0];opened=[];closed=[]
    class Page(io.BytesIO):
        status=200
        def getheader(self,key,default=None):return 'text/plain' if key=='Content-Type' else default
        def read(self,*a):pytest.fail('Large blocking read bypasses overall deadline')
        def read1(self,*a):tick[0]+=2;return b'x'
    page=Page(b'fixture')
    class Connection:
        sock=SimpleNamespace(settimeout=lambda value:None)
        def set_tunnel(self,*a):pass
        def request(self,*a,**kw):pass
        def getresponse(self):return page
        def close(self):pass
    monkeypatch.setattr(web_fetch.time,'monotonic',lambda:tick[0])
    monkeypatch.setattr(web_fetch,'public_address',lambda *a:'8.8.8.8')
    monkeypatch.setattr(web_fetch,'proxy_connection',lambda *a:Connection())
    with pytest.raises(TimeoutError):web_fetch.fetch('https://example.org',timeout=3,on_open=opened.append,on_close=closed.append)
    assert tick[0]==4 and set(opened)==set(closed) and page.closed


def test_search_stdout_preserves_all_ten_results_and_shares_full_text(tmp_path,monkeypatch,capsys):
    monkeypatch.chdir(tmp_path)
    value=dict(web_budget=dict(remaining=19),results=[dict(title=f'Title {i}',url=f'https://example.org/{i}',
        summary='s'*2500,content='FULL_BODY_'+str(i)+'x'*10000) for i in range(10)])
    tools.print_web('search',value)
    out=capsys.readouterr().out
    assert len(out.encode())<24000
    rows=[json.loads(line) for line in out.splitlines()]
    assert len(rows)==11 and len(rows[1]['excerpt'])==1500
    assert rows[-1]['url'].endswith('/9')
    saved=json.loads(open(rows[0]['full_result_file']).read())
    assert saved==value


def test_concurrent_search_artifacts_do_not_overwrite(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    with ThreadPoolExecutor(8) as pool:paths=list(pool.map(lambda i:tools.save_web('search',{'i':i}),range(20)))
    assert len(set(paths))==20
    assert sorted(json.loads(open(p).read())['i'] for p in paths)==list(range(20))


def fetch_page(monkeypatch,body,content_type,status=200):
    class Page(io.BytesIO):
        def getheader(self,key,default=None):return content_type if key=='Content-Type' else default
    page=Page(body);page.status=status
    class Connection:
        sock=SimpleNamespace(settimeout=lambda value:None)
        def set_tunnel(self,*a):pass
        def request(self,*a,**kw):pass
        def getresponse(self):return page
        def close(self):pass
    monkeypatch.setattr(web_fetch,'public_address',lambda *a:'8.8.8.8')
    monkeypatch.setattr(web_fetch,'proxy_connection',lambda *a:Connection())
    return web_fetch.fetch('https://example.org/data')


@pytest.mark.parametrize('content_type,body',[
    ('application/json; charset=utf-8',b'{"query":{"search":[{"title":"Lynmouth"}]}}'),
    ('text/x-wiki; charset=UTF-8',b"'''Lynmouth''' is a village <ref>x</ref>"),
    ('text/csv',b'year,value\n2020,1.5\n'),
    ('application/rss+xml',b'<rss><item><title>t</title></item></rss>'),
    ('application/ld+json',b'{"@type":"Dataset"}')])
def test_structured_text_formats_are_returned_verbatim(monkeypatch,content_type,body):
    # Retained HDR failures were Wikipedia API JSON and action=raw wikitext.
    value=fetch_page(monkeypatch,body,content_type)
    assert value['content']==body.decode() and value['title']==''


@pytest.mark.parametrize('content_type',['application/pdf','image/png','application/octet-stream',
    'application/zip','','image/svg+xml'])
def test_binary_or_untyped_responses_remain_unsupported(monkeypatch,content_type):
    with pytest.raises(web_fetch.FetchFailure) as error:fetch_page(monkeypatch,b'%PDF-1.7',content_type)
    assert error.value.reason=='unsupported_content_type' and error.value.http_status==200


def test_declared_charset_is_decoded_and_bytes_codecs_are_ignored(monkeypatch):
    assert fetch_page(monkeypatch,'café'.encode('latin-1'),'text/plain; charset=ISO-8859-1')['content']=='café'
    assert fetch_page(monkeypatch,b'plain','text/plain; charset=zlib')['content']=='plain'


def test_fetch_failure_reasons_do_not_mislabel_tls_protocol_or_dns_errors(monkeypatch):
    import http.client,ssl
    reason=web_fetch.failure_reason
    assert reason(ssl.SSLCertVerificationError('hostname mismatch'))=='tls_certificate_error'
    assert reason(ssl.SSLError('handshake'))=='tls_error'
    assert reason(http.client.IncompleteRead(b''))=='truncated_body'
    assert reason(http.client.LineTooLong('header line'))=='http_protocol_error'
    assert reason(http.client.RemoteDisconnected('closed'))=='connection_error'
    assert reason(OSError('Tunnel connection failed: 502 Bad Gateway'))=='proxy_connect_failed'
    assert reason(web_fetch.FetchCancelled('closing'))=='cancelled'
    assert reason(web_fetch.ProxyUnavailable('gone'))=='proxy_unavailable'
    assert reason(TimeoutError('late'))=='timeout'
    assert reason(UnicodeError('idna'))=='invalid_target'
    def missing(*a,**kw):raise web_fetch.DNSError('dns_resolution_failed')
    monkeypatch.setattr(web_fetch,'resolve_dns',missing)
    with pytest.raises(web_fetch.FetchFailure) as error:web_fetch.public_address('missing.example',443,1)
    assert error.value.reason=='dns_resolution_failed'


@pytest.mark.parametrize('failure,reason',[('incomplete','truncated_body'),('tls','tls_certificate_error')])
def test_gateway_reports_protocol_and_tls_fetch_failures_as_known_free_failures(tmp_path,monkeypatch,failure,reason):
    import http.client,ssl
    def failed(url,**kw):
        raise http.client.IncompleteRead(b'') if failure=='incomplete' else ssl.SSLCertVerificationError('mismatch')
    monkeypatch.setattr(web_fetch,'fetch',failed)
    with cg.CredentialGateway('synthetic',web_limit=1,ledger_path=tmp_path/'ledger') as gateway:
        with pytest.raises(urllib.error.HTTPError) as error:post(gateway,'/v1/tools/fetch',{'url':'https://example.org'})
        document=json.loads(error.value.read());error.value.close()
    assert error.value.code==502 and document['fetch_failure_reason']==reason
    assert document['web_budget']['remaining']==1 and gateway.summary()['web_reservations']==0
    record=json.loads((tmp_path/'ledger').read_text().splitlines()[-1])
    assert record['fetch_failure_reason']==reason and record['outcome']=='rejected' and record['web_success'] is False
    assert 'example.org' not in (tmp_path/'ledger').read_text()


@pytest.mark.parametrize('stage',['clash_dns_connect','PRIVATE_PAYLOAD'])
def test_gateway_records_only_allowlisted_failure_stages_without_retry(tmp_path,monkeypatch,stage):
    calls=[]
    def failed(url,**kw):
        calls.append(url)
        raise web_fetch.ProxyUnavailable('PRIVATE_MESSAGE',stage)
    monkeypatch.setattr(web_fetch,'fetch',failed)
    ledger=tmp_path/'ledger'
    with cg.CredentialGateway('synthetic',web_limit=1,ledger_path=ledger) as gateway:
        with pytest.raises(urllib.error.HTTPError) as error:
            post(gateway,'/v1/tools/fetch',{'url':'https://example.org'})
        document=json.loads(error.value.read());error.value.close()
    record=json.loads(ledger.read_text().splitlines()[-1])
    assert record['web_proxy_unavailable'] is True and record['web_refunded'] is True
    expected=stage if stage=='clash_dns_connect' else None
    assert record.get('fetch_failure_stage')==document['fetch_failure_stage']==expected
    assert len(calls)==1 and 'PRIVATE' not in ledger.read_text()+json.dumps(document)


def test_client_timeout_outlasts_host_fetch_deadline(monkeypatch):
    captured={}
    def run(argv,**kw):
        captured.update(argv=argv,timeout=kw['timeout'])
        return SimpleNamespace(returncode=0,stdout='{"web_budget":{}}\n200')
    monkeypatch.setattr(tools.subprocess,'run',run)
    tools.json_post('http://127.0.0.1:8765/v1/tools/fetch',{'url':'https://example.org'},'ephemeral')
    limit=int(captured['argv'][captured['argv'].index('--max-time')+1])
    assert limit==tools.CLIENT_TIMEOUT_SECONDS==web_policy.CLIENT_TIMEOUT_SECONDS
    assert limit>web_policy.FETCH_TIMEOUT_SECONDS and captured['timeout']>limit
    assert web_policy.configuration()['client_timeout_seconds']==limit


def test_completed_web_result_is_printed_even_when_sharing_fails(tmp_path,monkeypatch,capsys):
    blocked=tmp_path/'not-a-directory';blocked.write_text('')
    monkeypatch.setattr(tools,'share_root',lambda:blocked/'web')
    value=dict(web_budget=dict(remaining=3),results=[dict(title='T',url='https://example.org',summary='kept')])
    tools.print_web('search',value)
    rows=[json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert rows[0]['full_result_file'] is None and rows[0]['full_result_file_error']
    assert rows[1]['excerpt']=='kept'


def test_shared_web_files_use_workspace_when_present_else_cwd(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    workspace=tools.Path('/workspace')
    expected=workspace/'web' if workspace.is_dir() and tools.os.access(workspace,tools.os.W_OK) else tmp_path/'web'
    assert tools.share_root()==expected
