"""Bounded host GET through the local-Mac tunnel, with pinned public targets."""

from html.parser import HTMLParser
import http.client
import ipaddress
import math
import os
import socket
import ssl
import stat
import threading
import time
import urllib.parse

from harness.runtime_support.web_policy import FETCH_CHARS, FETCH_TIMEOUT_SECONDS, PROXY_SOCKET, allowed_url
from harness.runtime_support.dns_transport import resolve as resolve_dns, DNSError

HTML_TYPES = {'text/html', 'application/xhtml+xml'}
ACCEPT = ('text/html,application/xhtml+xml,text/plain;q=0.9,application/json;q=0.9,'
          'application/xml;q=0.8,text/*;q=0.8')


class ProxyUnavailable(OSError):
    def __init__(self, message, stage=None):
        super().__init__(message)
        self.stage=stage


class FetchCancelled(OSError):
    pass


class FetchFailure(ValueError):
    def __init__(self,reason,http_status=None):
        super().__init__(reason)
        self.reason,self.http_status=reason,http_status


class RequestDeadline:
    """Interrupt slow CONNECT, TLS and header reads, not only body iteration."""
    def __init__(self, timeout):
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('Positive finite fetch timeout required')
        self.expired = threading.Event()
        self.lock = threading.Lock()
        self.resources = []
        self.timer = threading.Timer(timeout, self.expire)
        self.timer.daemon = True

    @staticmethod
    def abort(resource):
        sock = getattr(resource, 'sock', resource)
        if sock is not None and hasattr(sock, 'shutdown'):
            try:sock.shutdown(socket.SHUT_RDWR)
            except OSError:pass

    def watch(self, resource):
        with self.lock:
            self.resources.append(resource)
            expired = self.expired.is_set()
        if expired:
            self.abort(resource)
            raise TimeoutError('Fetch deadline exceeded')

    def expire(self):
        with self.lock:
            self.expired.set()
            resources = list(self.resources)
        for resource in resources:
            self.abort(resource)

    def __enter__(self):
        self.timer.start()
        return self

    def __exit__(self, *args):
        self.timer.cancel()
        self.timer.join()


def failure_reason(error):
    """Payload-free reason code; never copies URLs, bodies or exception text."""
    if isinstance(error,FetchFailure):return error.reason
    if isinstance(error,FetchCancelled):return 'cancelled'
    if isinstance(error,ProxyUnavailable):return 'proxy_unavailable'
    if isinstance(error,TimeoutError):return 'timeout'
    # SSLCertVerificationError is also a ValueError; classify TLS before generic errors.
    if isinstance(error,ssl.SSLCertVerificationError):return 'tls_certificate_error'
    if isinstance(error,ssl.SSLError):return 'tls_error'
    if isinstance(error,http.client.IncompleteRead):return 'truncated_body'
    if isinstance(error,ConnectionError):return 'connection_error'
    if isinstance(error,http.client.HTTPException):return 'http_protocol_error'
    if isinstance(error,OSError):
        # http.client reports a non-200 proxy CONNECT reply with this fixed prefix.
        return 'proxy_connect_failed' if str(error).startswith('Tunnel connection failed') else 'transport_error'
    if isinstance(error,UnicodeError):return 'invalid_target'
    return 'internal_error'


def textual(media_type):
    """Text and structured-text formats are readable evidence; binary formats are not."""
    main,_,sub=media_type.partition('/')
    return bool(sub) and (main=='text' or (main=='application' and (
        sub in {'json','xml'} or sub.endswith(('+json','+xml')))))


def decode(body,content_type):
    encoding='utf-8'
    for parameter in content_type.split(';')[1:]:
        name,_,value=parameter.partition('=')
        if name.strip().lower()=='charset':
            candidate=value.strip().strip('"\'').lower()
            try:
                # Non-empty probe: CPython skips the text-encoding check for b''.
                b'a'.decode(candidate,'replace')  # Rejects unknown and bytes-to-bytes codecs.
                encoding=candidate
            except (LookupError,ValueError):
                pass
    return body.decode(encoding,errors='replace')


def check_proxy(path=PROXY_SOCKET):
    try:parent=path.parent.lstat();value=path.lstat()
    except OSError:raise ProxyUnavailable('Local Clash tunnel socket unavailable','fetch_socket_check') from None
    if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid!=os.getuid()
            or stat.S_IMODE(parent.st_mode)!=0o700 or not stat.S_ISSOCK(value.st_mode)
            or value.st_uid!=os.getuid() or stat.S_IMODE(value.st_mode)!=0o600):
        raise ProxyUnavailable('Proxy requires owned mode-0700 directory and mode-0600 Unix socket','fetch_socket_check')


def open_proxy(path,timeout):
    check_proxy(path)
    client=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    client.settimeout(timeout)
    try:client.connect(str(path))
    except OSError:
        client.close();raise ProxyUnavailable('Local Clash tunnel connection unavailable','fetch_tunnel_connect') from None
    return client


class ProxyHTTPConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock=self._create_connection((self.host,self.port),self.timeout,self.source_address)
        if self._tunnel_host:self._tunnel()


class ProxyHTTPSConnection(http.client.HTTPSConnection):
    def connect(self):
        ProxyHTTPConnection.connect(self)
        # CONNECT uses a pinned public IP; TLS still verifies the original host.
        self.sock=self._context.wrap_socket(self.sock,server_hostname=self.host,do_handshake_on_connect=False)
        if getattr(self, '_on_socket', None):self._on_socket(self.sock)
        self.sock.do_handshake()


def proxy_connection(host,port,secure,timeout,path,on_socket=None):
    cls=ProxyHTTPSConnection if secure else ProxyHTTPConnection
    connection=cls(host,port,timeout=timeout)
    def connect(_dest,timeout=None,source_address=None):
        sock=open_proxy(path,timeout)
        try:
            if on_socket is not None:on_socket(sock)
        except BaseException:
            sock.close()
            raise
        return sock
    connection._create_connection=connect
    connection._on_socket=on_socket
    return connection


def check_ready(timeout=10):
    """TLS-only admission check; no model/search API or page request."""
    with RequestDeadline(timeout) as deadline:
        try:
            result = _check_ready(timeout, deadline)
            if deadline.expired.is_set():raise TimeoutError('Proxy readiness deadline exceeded')
            return result
        except Exception:
            if deadline.expired.is_set():raise TimeoutError('Proxy readiness deadline exceeded') from None
            raise


def check_ready_with_recovery(timeout=10, *, attempts=3, delay=1):
    """Bounded retries of free TLS admission only, never of a solver or web GET."""
    if type(attempts) is not int or not 1 <= attempts <= 3 or delay < 0:
        raise ValueError('Readiness requires 1-3 probes and a nonnegative delay')
    failures = []
    for index in range(attempts):
        try:
            receipt = check_ready(timeout)
            return dict(receipt, readiness_attempts=index + 1, transient_failures=failures)
        except (OSError, RuntimeError) as error:
            failures.append(type(error).__name__)
            if index + 1 == attempts:
                raise
            time.sleep(delay)


def _check_ready(timeout, deadline):
    check_proxy()
    start=time.monotonic()
    address=public_address('en.wikipedia.org',443,timeout)
    remaining=timeout-(time.monotonic()-start)
    if remaining<=0:raise ProxyUnavailable('Proxy readiness deadline exceeded')
    connection=proxy_connection('en.wikipedia.org',443,True,remaining,PROXY_SOCKET,deadline.watch)
    deadline.watch(connection)
    connection.set_tunnel(address,443)
    try:connection.connect()
    finally:connection.close()
    return dict(transport='local-clash-unix',socket=str(PROXY_SOCKET),tls_verified=True,
                target='en.wikipedia.org:443',model_calls=0)


class PageText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden=0
        self.parts=[]
        self.title=[]
        self.in_title=False

    def handle_starttag(self,tag,attrs):
        if tag in {'script','style','noscript','template'}:self.hidden+=1
        if tag=='title':self.in_title=True
        if not self.hidden and tag in {'p','div','br','li','h1','h2','h3','tr'}:self.parts.append('\n')

    def handle_endtag(self,tag):
        if tag in {'script','style','noscript','template'}:self.hidden=max(0,self.hidden-1)
        if tag=='title':self.in_title=False

    def handle_data(self,data):
        if not self.hidden:
            self.parts.append(data)
            if self.in_title:self.title.append(data)


def public_address(host,port,timeout):
    try:addresses=resolve_dns(host,timeout)
    except DNSError as error:
        if error.reason=='proxy_unavailable':raise ProxyUnavailable('DNS tunnel unavailable',error.stage) from None
        failure=FetchFailure(error.reason)
        failure.stage=error.stage
        raise failure from None
    if not addresses or any(not ipaddress.ip_address(a).is_global or ipaddress.ip_address(a).is_multicast
                            or ipaddress.ip_address(a).is_reserved for a in addresses):
        raise FetchFailure('non_public_address')
    return next((a for a in addresses if ipaddress.ip_address(a).version==4),addresses[0])


def fetch(url,*,timeout=FETCH_TIMEOUT_SECONDS,proxy_socket=PROXY_SOCKET,cancel=None,on_open=None,on_close=None):
    with RequestDeadline(timeout) as guard:
        try:
            result = _fetch(url,timeout=timeout,proxy_socket=proxy_socket,cancel=cancel,
                            on_open=on_open,on_close=on_close,guard=guard)
            if guard.expired.is_set():raise TimeoutError('Fetch deadline exceeded')
            return result
        except Exception:
            if guard.expired.is_set():raise TimeoutError('Fetch deadline exceeded') from None
            raise


def _fetch(url,*,timeout,proxy_socket,cancel,on_open,on_close,guard):
    deadline=time.monotonic()+timeout
    def remaining():
        if cancel is not None and cancel.is_set():raise FetchCancelled('Fetch cancelled')
        value=deadline-time.monotonic()
        if value<=0:raise TimeoutError('Fetch deadline exceeded')
        return value
    for hop in range(6):
        if not allowed_url(url):raise FetchFailure('url_policy_rejected')
        parsed=urllib.parse.urlsplit(url)
        port=parsed.port or (443 if parsed.scheme=='https' else 80)
        address=public_address(parsed.hostname,port,remaining())
        connection=proxy_connection(parsed.hostname,port,parsed.scheme=='https',remaining(),proxy_socket,guard.watch)
        connection.set_tunnel(address,port)
        response=None
        try:
            guard.watch(connection)
            if on_open is not None:on_open(connection)
            remaining()
            path=urllib.parse.urlunsplit(('', '',parsed.path or '/',parsed.query,''))
            path=urllib.parse.quote(path,safe="/%:@!$&'()*+,;=-._~?")
            connection.request('GET',path,headers={'User-Agent':'MAS-benchmark-research/1.0',
                'Host':parsed.netloc,'Accept':ACCEPT,'Accept-Encoding':'identity'})
            transport=connection.sock
            guard.watch(transport)
            transport.settimeout(remaining())
            response=connection.getresponse()
            if on_open is not None:on_open(response)
            if response.status in {301,302,303,307,308}:
                location=response.getheader('Location')
                if not location or hop==5:raise FetchFailure('redirect_limit_or_missing_location',response.status)
                url=urllib.parse.urljoin(url,location)
                continue
            if response.status!=200:raise FetchFailure('target_http_error',response.status)
            header=response.getheader('Content-Type','')
            content_type=header.split(';')[0].strip().lower()
            if not textual(content_type):
                raise FetchFailure('unsupported_content_type',response.status)
            if response.getheader('Content-Encoding','identity').lower()!='identity':
                raise FetchFailure('unsupported_content_encoding',response.status)
            chunks=[];size=0
            while True:
                if getattr(response,'isclosed',lambda:False)():
                    if getattr(response,'length',0):raise FetchFailure('truncated_body',response.status)
                    break
                transport.settimeout(remaining())
                chunk=response.read1(min(32768,2*1024*1024+1-size))
                if not chunk:
                    if getattr(response,'length',0):raise FetchFailure('truncated_body',response.status)
                    break
                chunks.append(chunk);size+=len(chunk)
                if size>2*1024*1024:raise FetchFailure('body_size_limit',response.status)
            text=decode(b''.join(chunks),header)
            title=''
            # Only HTML is markup to strip; JSON, XML, CSV and plain text stay verbatim.
            if content_type in HTML_TYPES:
                parser=PageText();parser.feed(text)
                title=' '.join(''.join(parser.title).split())[:500]
                text='\n'.join(line for part in ''.join(parser.parts).splitlines() if (line:=' '.join(part.split())))
            if not text.strip():raise FetchFailure('empty_extracted_text',response.status)
            return dict(url=url,title=title,content=text[:FETCH_CHARS],truncated=len(text)>FETCH_CHARS)
        finally:
            try:
                if response is not None:
                    try:response.close()
                    finally:
                        if on_close is not None:on_close(response)
            finally:
                try:connection.close()
                finally:
                    if on_close is not None:on_close(connection)
