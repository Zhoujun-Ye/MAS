"""Bounded host GET through the local-Mac tunnel, with pinned public targets."""

from html.parser import HTMLParser
import http.client
import ipaddress
import queue
import os
import socket
import ssl
import stat
import threading
import time
import urllib.parse

from harness.runtime_support.web_policy import FETCH_CHARS, FETCH_TIMEOUT_SECONDS, PROXY_SOCKET, allowed_url

HTML_TYPES = {'text/html', 'application/xhtml+xml'}
ACCEPT = ('text/html,application/xhtml+xml,text/plain;q=0.9,application/json;q=0.9,'
          'application/xml;q=0.8,text/*;q=0.8')


class ProxyUnavailable(OSError):
    pass


class FetchCancelled(OSError):
    pass


class FetchFailure(ValueError):
    def __init__(self,reason,http_status=None):
        super().__init__(reason)
        self.reason,self.http_status=reason,http_status


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
    except OSError:raise ProxyUnavailable('Local Clash tunnel socket unavailable') from None
    if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid!=os.getuid()
            or stat.S_IMODE(parent.st_mode)!=0o700 or not stat.S_ISSOCK(value.st_mode)
            or value.st_uid!=os.getuid() or stat.S_IMODE(value.st_mode)!=0o600):
        raise ProxyUnavailable('Proxy requires owned mode-0700 directory and mode-0600 Unix socket')


def open_proxy(path,timeout):
    check_proxy(path)
    client=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    client.settimeout(timeout)
    try:client.connect(str(path))
    except OSError:
        client.close();raise ProxyUnavailable('Local Clash tunnel connection unavailable') from None
    return client


class ProxyHTTPConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock=self._create_connection((self.host,self.port),self.timeout,self.source_address)
        if self._tunnel_host:self._tunnel()


class ProxyHTTPSConnection(http.client.HTTPSConnection):
    def connect(self):
        ProxyHTTPConnection.connect(self)
        # CONNECT uses a pinned public IP; TLS still verifies the original host.
        self.sock=self._context.wrap_socket(self.sock,server_hostname=self.host)


def proxy_connection(host,port,secure,timeout,path):
    cls=ProxyHTTPSConnection if secure else ProxyHTTPConnection
    connection=cls(host,port,timeout=timeout)
    connection._create_connection=lambda _dest,timeout=None,source_address=None:open_proxy(path,timeout)
    return connection


def check_ready(timeout=10):
    """TLS-only admission check; no model/search API or page request."""
    check_proxy()
    start=time.monotonic()
    address=public_address('en.wikipedia.org',443,timeout)
    remaining=timeout-(time.monotonic()-start)
    if remaining<=0:raise ProxyUnavailable('Proxy readiness deadline exceeded')
    connection=proxy_connection('en.wikipedia.org',443,True,remaining,PROXY_SOCKET)
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
    result=queue.Queue(maxsize=1)
    def resolve():
        try:result.put(socket.getaddrinfo(host,port,type=socket.SOCK_STREAM))
        except Exception as error:result.put(error)
    threading.Thread(target=resolve,daemon=True).start()
    try:rows=result.get(timeout=timeout)
    except queue.Empty:raise TimeoutError('DNS deadline exceeded') from None
    if isinstance(rows,UnicodeError):raise FetchFailure('invalid_target') from None
    if isinstance(rows,OSError):raise FetchFailure('dns_resolution_failed') from None
    if isinstance(rows,Exception):raise rows
    addresses=[row[4][0] for row in rows]
    if not addresses or any(not ipaddress.ip_address(a).is_global or ipaddress.ip_address(a).is_multicast
                            or ipaddress.ip_address(a).is_reserved for a in addresses):
        raise FetchFailure('non_public_address')
    return next((a for a in addresses if ipaddress.ip_address(a).version==4),addresses[0])


def fetch(url,*,timeout=FETCH_TIMEOUT_SECONDS,proxy_socket=PROXY_SOCKET,cancel=None,on_open=None,on_close=None):
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
        connection=proxy_connection(parsed.hostname,port,parsed.scheme=='https',remaining(),proxy_socket)
        connection.set_tunnel(address,port)
        response=None
        try:
            if on_open is not None:on_open(connection)
            remaining()
            path=urllib.parse.urlunsplit(('', '',parsed.path or '/',parsed.query,''))
            path=urllib.parse.quote(path,safe="/%:@!$&'()*+,;=-._~?")
            connection.request('GET',path,headers={'User-Agent':'MAS-benchmark-research/1.0',
                'Host':parsed.netloc,'Accept':ACCEPT,'Accept-Encoding':'identity'})
            transport=connection.sock
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
