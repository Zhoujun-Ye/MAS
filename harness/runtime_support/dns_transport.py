"""Restricted DNS bridge to the Mac's existing Clash resolver; no fallback."""

from contextlib import contextmanager
import http.client
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import socket
import socketserver
import stat
import threading
import time
import urllib.parse

PROTOCOL = 'mas-clash-dns-v1'
DNS_SOCKET = Path.home() / '.cache/mas-web/dns.sock'
MAX_BYTES = 8192
MAX_ADDRESSES = 64
STAGES = {'dns_socket_check','dns_bridge_connect','dns_bridge_reply',
          'clash_dns_connect','clash_dns_http','clash_dns_decode','clash_dns_query'}


class DNSError(ValueError):
    def __init__(self, reason, stage=None):
        super().__init__(reason)
        self.reason = reason
        self.stage = stage if stage in STAGES else None


def hostname(value):
    if not isinstance(value, str) or '%' in value:
        raise DNSError('invalid_target')
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        pass
    try:
        value = value.rstrip('.').encode('idna').decode('ascii').lower()
    except UnicodeError:
        raise DNSError('invalid_target') from None
    if (len(value) > 253 or '.' not in value or
            any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', p)
                for p in value.split('.'))):
        raise DNSError('invalid_target')
    return value


def public_addresses(values):
    if not isinstance(values, list) or not 1 <= len(values) <= MAX_ADDRESSES:
        raise DNSError('dns_resolution_failed')
    result = []
    for value in values:
        try:
            if not isinstance(value, str) or '%' in value:
                raise ValueError()
            address = ipaddress.ip_address(value)
        except ValueError:
            raise DNSError('dns_response_invalid') from None
        if not address.is_global or address.is_multicast or address.is_reserved:
            raise DNSError('non_public_address')
        if str(address) not in result:
            result.append(str(address))
    return result


def check_socket(path):
    try:
        parent, value = path.parent.lstat(), path.lstat()
    except OSError:
        raise DNSError('proxy_unavailable','dns_socket_check') from None
    if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid()
            or stat.S_IMODE(parent.st_mode) != 0o700 or not stat.S_ISSOCK(value.st_mode)
            or value.st_uid != os.getuid() or stat.S_IMODE(value.st_mode) != 0o600):
        raise DNSError('proxy_unavailable','dns_socket_check')


def line(client, deadline):
    data = b''
    while b'\n' not in data:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise DNSError('dns_timeout')
        client.settimeout(remaining)
        chunk = client.recv(min(1024, MAX_BYTES + 1 - len(data)))
        if not chunk or len(data) + len(chunk) > MAX_BYTES:
            raise DNSError('dns_response_invalid')
        data += chunk
    first, rest = data.split(b'\n', 1)
    if rest:
        raise DNSError('dns_response_invalid')
    try:
        return json.loads(first)
    except (ValueError, UnicodeError):
        raise DNSError('dns_response_invalid') from None


def resolve(host, timeout, path=DNS_SOCKET):
    host = hostname(host)
    try:
        return public_addresses([str(ipaddress.ip_address(host))])
    except ValueError as error:
        if isinstance(error, DNSError):
            raise
    if not math.isfinite(timeout) or timeout <= 0:
        raise DNSError('dns_timeout')
    deadline = time.monotonic() + min(timeout, 8)
    check_socket(path)
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    stage = 'dns_bridge_connect'
    try:
        client.settimeout(max(0.001, deadline - time.monotonic()))
        client.connect(str(path))
        client.sendall((json.dumps(dict(protocol=PROTOCOL, host=host)) + '\n').encode())
        stage = 'dns_bridge_reply'
        result = line(client, deadline)
        if not isinstance(result, dict) or result.get('protocol') != PROTOCOL or result.get('host') != host:
            raise DNSError('dns_response_invalid')
        if result.get('error'):
            reason = result['error']
            raise DNSError(reason if reason in {'dns_timeout','dns_resolution_failed',
                'dns_response_invalid','non_public_address','invalid_target','proxy_unavailable'} else 'dns_response_invalid',
                result.get('stage'))
        return public_addresses(result.get('addresses'))
    except DNSError as error:
        if error.stage is None:error.stage=stage
        raise
    except socket.timeout:
        raise DNSError('dns_timeout',stage) from None
    except OSError:
        raise DNSError('proxy_unavailable',stage) from None
    finally:
        client.close()


def controller_query(path, host, kind, timeout):
    """Only this fixed DNS API path is reachable; never forward the control API."""
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    expired = threading.Event()
    def expire():
        expired.set()
        try:
            client.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
    timer = threading.Timer(timeout, expire)
    timer.daemon = True
    connection = http.client.HTTPConnection('localhost', timeout=timeout)
    stage = 'clash_dns_connect'
    try:
        client.settimeout(timeout)
        timer.start()
        client.connect(str(path))
        stage = 'clash_dns_http'
        connection.sock = client
        query = urllib.parse.urlencode(dict(name=host, type=kind))
        connection.request('GET', '/dns/query?' + query, headers={'Connection':'close'})
        response = connection.getresponse()
        body = response.read(65537)
        if response.status != 200 or len(body) > 65536:
            raise DNSError('dns_response_invalid')
        stage = 'clash_dns_decode'
        value = json.loads(body)
        if expired.is_set():
            raise DNSError('dns_timeout')
        if (not isinstance(value, dict) or value.get('Status') != 0 or value.get('TC')
                or not isinstance(value.get('Question'), list) or len(value['Question']) != 1):
            raise DNSError('dns_resolution_failed')
        question = value['Question'][0]
        if (not isinstance(question, dict) or hostname(question.get('Name')) != host
                or question.get('Qtype') != (1 if kind == 'A' else 28) or question.get('Qclass') != 1):
            raise DNSError('dns_response_invalid')
        answers = value.get('Answer') or []
        if not isinstance(answers, list) or len(answers) > MAX_ADDRESSES:
            raise DNSError('dns_response_invalid')
        if not all(isinstance(a, dict) for a in answers):
            raise DNSError('dns_response_invalid')
        return [a.get('data') for a in answers if a.get('type') == (1 if kind == 'A' else 28)]
    except DNSError as error:
        if error.stage is None:error.stage=stage
        raise
    except socket.timeout:
        raise DNSError('dns_timeout',stage) from None
    except ValueError:
        raise DNSError('dns_response_invalid',stage) from None
    except http.client.HTTPException:
        raise DNSError('dns_timeout' if expired.is_set() else 'dns_response_invalid',stage) from None
    except OSError:
        raise DNSError('dns_timeout' if expired.is_set() else 'proxy_unavailable',stage) from None
    finally:
        timer.cancel()
        timer.join()
        connection.close()
        client.close()


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        host = None
        try:
            request = line(self.request, time.monotonic() + 2)
            if not isinstance(request, dict) or set(request) != {'protocol','host'} or request['protocol'] != PROTOCOL:
                raise DNSError('dns_response_invalid')
            host = hostname(request['host'])
            addresses = []
            for kind in ('A', 'AAAA'):
                addresses.extend(controller_query(self.server.controller, host, kind, 3))
            result = dict(addresses=public_addresses(addresses))
        except Exception as error:
            result = dict(error=error.reason if isinstance(error, DNSError) else 'dns_response_invalid')
            if isinstance(error,DNSError) and error.stage:result['stage']=error.stage
        payload = dict(result, protocol=PROTOCOL, host=host)
        try:
            self.request.sendall((json.dumps(payload) + '\n').encode())
        except OSError:
            pass


class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    request_queue_size = 16
    def __init__(self, path, controller):
        self.controller = controller
        self.slots = threading.BoundedSemaphore(16)
        super().__init__(str(path), Handler)

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()


@contextmanager
def bridge(path, controller=None):
    path = Path(path)
    controller = controller or Path(f'/var/run/clash-verge-service/users/{os.getuid()}/verge-mihomo.sock')
    parent = path.parent.lstat()
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) != 0o700:
        raise DNSError('proxy_unavailable')
    if path.exists() or path.is_symlink():
        check_socket(path)
        client = socket.socket(socket.AF_UNIX)
        client.settimeout(1)
        try:
            client.connect(str(path))
        except ConnectionRefusedError:
            path.unlink()
        else:
            raise DNSError('proxy_unavailable')
        finally:
            client.close()
    server = Server(path, controller)
    path.chmod(0o600)
    identity = path.stat().st_ino
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        try:
            if path.lstat().st_ino == identity:
                path.unlink()
        except FileNotFoundError:
            pass
