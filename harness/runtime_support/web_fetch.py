"""Bounded host GET through the local-Mac tunnel, with pinned public targets."""

from html.parser import HTMLParser
import http.client
import ipaddress
import queue
import os
import socket
import stat
import threading
import time
import urllib.parse

from harness.runtime_support.web_policy import FETCH_CHARS, PROXY_SOCKET, allowed_url


class ProxyUnavailable(OSError):
    pass


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
    if isinstance(rows,Exception):raise rows
    addresses=[row[4][0] for row in rows]
    if not addresses or any(not ipaddress.ip_address(a).is_global or ipaddress.ip_address(a).is_multicast
                            or ipaddress.ip_address(a).is_reserved for a in addresses):
        raise ValueError('Only public destination addresses are allowed')
    return next((a for a in addresses if ipaddress.ip_address(a).version==4),addresses[0])


def fetch(url,*,timeout=30,proxy_socket=PROXY_SOCKET):
    deadline=time.monotonic()+timeout
    def remaining():
        value=deadline-time.monotonic()
        if value<=0:raise TimeoutError('Fetch deadline exceeded')
        return value
    for hop in range(6):
        if not allowed_url(url):raise ValueError('Blocked or invalid web URL')
        parsed=urllib.parse.urlsplit(url)
        port=parsed.port or (443 if parsed.scheme=='https' else 80)
        address=public_address(parsed.hostname,port,remaining())
        connection=proxy_connection(parsed.hostname,port,parsed.scheme=='https',remaining(),proxy_socket)
        connection.set_tunnel(address,port)
        try:
            path=urllib.parse.urlunsplit(('', '',parsed.path or '/',parsed.query,''))
            path=urllib.parse.quote(path,safe="/%:@!$&'()*+,;=-._~?")
            connection.request('GET',path,headers={'User-Agent':'MAS-benchmark-research/1.0',
                'Host':parsed.netloc,'Accept':'text/html,text/plain,application/xhtml+xml','Accept-Encoding':'identity'})
            transport=connection.sock
            transport.settimeout(remaining())
            response=connection.getresponse()
            if response.status in {301,302,303,307,308}:
                location=response.getheader('Location')
                if not location or hop==5:raise ValueError('Invalid or excessive redirect')
                url=urllib.parse.urljoin(url,location)
                continue
            if response.status!=200:raise ValueError('Page returned HTTP '+str(response.status))
            content_type=response.getheader('Content-Type','').split(';')[0].lower()
            if content_type not in {'text/html','application/xhtml+xml','text/plain'}:
                raise ValueError('Unsupported page content type')
            if response.getheader('Content-Encoding','identity').lower()!='identity':
                raise ValueError('Unsupported compressed response')
            chunks=[];size=0
            while True:
                transport.settimeout(remaining())
                chunk=response.read(min(32768,2*1024*1024+1-size))
                if not chunk:break
                chunks.append(chunk);size+=len(chunk)
                if size>2*1024*1024:raise ValueError('Page exceeds 2 MiB')
            text=b''.join(chunks).decode('utf-8',errors='replace')
            title=''
            if content_type!='text/plain':
                parser=PageText();parser.feed(text)
                title=' '.join(''.join(parser.title).split())[:500]
                text='\n'.join(line for part in ''.join(parser.parts).splitlines() if (line:=' '.join(part.split())))
            if not text.strip():raise ValueError('Page has no extractable text')
            return dict(url=url,title=title,content=text[:FETCH_CHARS],truncated=len(text)>FETCH_CHARS)
        finally:
            connection.close()
