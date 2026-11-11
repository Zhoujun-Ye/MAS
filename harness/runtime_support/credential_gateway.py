"""Shared harness credential transport and host receipts; no model orchestration."""

from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import socket
import socketserver
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid

from harness.runtime_support import web_fetch, web_policy


ROUTES = {"/anthropic/v1/messages", "/anthropic/v1/messages/count_tokens",
          "/v1/tools/search", "/v1/tools/fetch"}
USAGE_FIELDS = {"input_tokens", "output_tokens", "total_tokens", "prompt_tokens", "completion_tokens",
                "cache_creation_input_tokens", "cache_read_input_tokens", "cached_tokens", "reasoning_tokens",
                "prompt_cache_hit_tokens", "prompt_cache_miss_tokens", "search_units", "credits", "requests",
                "input_tokens_details", "output_tokens_details", "prompt_tokens_details", "completion_tokens_details",
                "server_tool_use", "web_search_requests", "web_fetch_requests"}


def now():
    return datetime.now(timezone.utc).isoformat()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def open_upstream(request):
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(request, timeout=180)


def numeric_usage(value):
    if not isinstance(value, dict):
        return {}
    result = {}
    for name, item in value.items():
        if name not in USAGE_FIELDS:
            continue
        if isinstance(item, (int, float)) and not isinstance(item, bool) and 0 <= item < 1e18:
            result[name] = item
        elif isinstance(item, dict):
            nested = numeric_usage(item)
            if nested:
                result[name] = nested
    return result


class UsageObserver:
    """Observe bounded JSON/SSE metadata without retaining model or web content."""
    def __init__(self, streaming):
        self.streaming = streaming
        self.pending = b""
        self.usage = {}
        self.response_id = None
        self.overflow = False

    def observe(self, value):
        if not isinstance(value, dict):
            return
        self.usage.update(numeric_usage(value.get("usage")))
        identity = value.get("id")
        if isinstance(identity, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", identity):
            self.response_id = identity
        for name in ("message",):
            if isinstance(value.get(name), dict):
                self.observe(value[name])

    def parse(self, raw):
        try:
            self.observe(json.loads(raw))
        except (ValueError, UnicodeDecodeError):
            pass

    def feed(self, chunk):
        if self.overflow:
            return
        self.pending += chunk
        if self.streaming:
            while b"\n" in self.pending:
                line, self.pending = self.pending.split(b"\n", 1)
                if line.startswith(b"data:"):
                    self.parse(line[5:].strip())
        if len(self.pending) > 1024 * 1024:
            self.pending = b""
            self.overflow = True

    def finish(self):
        if not self.streaming and not self.overflow:
            self.parse(self.pending)
        self.pending = b""


class CredentialGateway:
    def __init__(self, key, *, bind="127.0.0.1", web_limit=0, unix_path=None, ledger_path=None):
        if not isinstance(key, str) or not key or not key.isascii() or any(c.isspace() for c in key):
            raise ValueError("Invalid provider credential format")
        if web_limit < 0:
            raise ValueError("Web limit must be nonnegative")
        self.key, self.token = key, secrets.token_urlsafe(32)
        self.web_limit, self.web_calls = web_limit, 0
        self.web_attempts=0
        self.web_attempt_limit=web_limit*2
        self.lock = threading.Lock()
        self.ledger_lock = threading.Lock()
        self.request_records = {}
        self.ledger_closed = False
        self.closing = threading.Event()
        self.activity_lock = threading.Lock()
        self.active_clients = set()
        self.active_responses = set()
        self.ledger_path = Path(ledger_path) if ledger_path is not None else (
            Path(unix_path).with_name("gateway-requests.jsonl") if unix_path is not None else None)
        self.ledger_fd = None
        if self.ledger_path is not None:
            self.ledger_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            self.ledger_fd = os.open(self.ledger_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_EXCL, 0o600)
        gateway = self

        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                super().setup()
                self.connection.settimeout(180)
                with gateway.activity_lock:
                    gateway.active_clients.add(self.connection)

            def finish(self):
                try:
                    super().finish()
                finally:
                    with gateway.activity_lock:
                        gateway.active_clients.discard(self.connection)

            def log_message(self, *args):
                pass

            def json_error(self, code, kind, message):
                self.record.update(http_status=code, outcome="rejected", error_type=kind)
                value=dict(type="error",error=dict(type=kind,message=message))
                if kind=='host_fetch_failed':
                    value.update(fetch_failure_reason=self.record.get('fetch_failure_reason'),
                                 fetch_failure_stage=self.record.get('fetch_failure_stage'),
                                 target_http_status=self.record.get('target_http_status'))
                if self.record.get('web_reserved'):value['web_budget']=gateway.settle_web(self.record)
                data = json.dumps(value).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                request_id = uuid.uuid4().hex
                self.record = dict(request_id=request_id, route="unrecognized", started_at=now(),
                    upstream_attempted=False, web_reserved=False, outcome="incomplete", origin="unverified",
                    http_status=None, usage=None, usage_status="unknown")
                observer = None
                response = None
                try:
                    parsed = urllib.parse.urlsplit(self.path)
                    if parsed.path in ROUTES:
                        self.record["route"] = parsed.path
                    gateway.receipt(dict(self.record, event="started"))
                    if gateway.closing.is_set():
                        self.json_error(503, "gateway_closed", "Run gateway is closing; no provider request sent")
                        return
                    token = self.headers.get("x-api-key", self.headers.get("Authorization", "").removeprefix("Bearer "))
                    if not token.isascii() or not hmac.compare_digest(token, gateway.token):
                        self.json_error(403, "authentication_error", "Invalid run credential")
                        return
                    if parsed.path not in ROUTES or parsed.query not in {"", "beta=true"} or parsed.scheme or parsed.netloc or parsed.fragment:
                        self.json_error(404, "route_not_allowed", "Route not allowed")
                        return
                    if self.headers.get("Transfer-Encoding") or len(self.headers.get_all("Content-Length", [])) != 1:
                        self.json_error(400, "invalid_request_error", "Ambiguous request framing")
                        return
                    try:
                        size = int(self.headers.get("Content-Length", "0"))
                    except ValueError:
                        size = -1
                    if not 0 < size <= 32 * 1024 * 1024:
                        self.json_error(413, "invalid_request_error", "Invalid body size")
                        return
                    body = self.rfile.read(size)
                    try:
                        payload = json.loads(body)
                        if len(body) != size or not isinstance(payload, dict):
                            raise ValueError()
                        if not parsed.path.startswith("/v1/tools/") and payload.get("model") not in {"deepseek-flash", "deepseek-flash[1m]"}:
                            raise ValueError()
                        if parsed.path=='/v1/tools/search':
                            query=payload.get('query')
                            if not isinstance(query,str) or not query.strip() or len(query)>128:raise ValueError()
                            if any(name in query.casefold() for name in ('dataclaw','hybriddeepresearch','kramabench')):raise ValueError()
                            payload=dict(query=query,count=web_policy.SEARCH_RESULTS,need_content=True)
                            body=json.dumps(payload).encode()
                        if parsed.path=='/v1/tools/fetch' and not web_policy.allowed_url(payload.get('url','')):
                            raise ValueError()
                    except (ValueError, TypeError):
                        self.json_error(400, "invalid_request_error", "Invalid payload or unauthorized model")
                        return
                    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + gateway.key,
                               "Accept-Encoding": "identity"}
                    config = payload.get("output_config")
                    effort = config.get("effort") if isinstance(config, dict) else None
                    self.record["request_effort"] = effort if effort in ("low", "medium", "high", "xhigh", "max") else None
                    if parsed.path.startswith("/anthropic/"):
                        headers["x-api-key"] = gateway.key
                        for name in ("anthropic-version", "anthropic-beta"):
                            if self.headers.get(name):
                                headers[name] = self.headers[name]
                    request = urllib.request.Request("https://api.deepseek.com" + self.path, data=body, headers=headers)
                    # Linearize dispatch commitment against shutdown without holding
                    # the lock across provider I/O. Committed calls may be chargeable.
                    with gateway.activity_lock:
                        if gateway.closing.is_set():
                            self.json_error(503, "gateway_closed", "Run gateway is closing; no provider request sent")
                            return
                        if parsed.path.startswith("/v1/tools/"):
                            with gateway.lock:
                                if gateway.web_calls >= gateway.web_limit or gateway.web_attempts>=gateway.web_attempt_limit:
                                    self.json_error(429, "run_web_limit_exhausted", "Run web request limit exhausted; no provider request sent; do not retry")
                                    return
                                gateway.web_calls += 1
                                gateway.web_attempts += 1
                                self.record.update(web_reserved=True, web_reservation=gateway.web_calls)
                        self.record.update(upstream_attempted=True, dispatched_at=now())
                        if parsed.path.startswith('/v1/tools/'):
                            fetching=parsed.path.endswith('/fetch')
                            self.record.update(web_backend='local-clash-unix' if fetching else 'deepseek',
                                estimated_cost_usd=0 if fetching else None,
                                cost_status='no paid fetch provider' if fetching else 'unknown')
                        gateway.receipt(dict(self.record, event="dispatched"))
                    if parsed.path.startswith('/v1/tools/'):
                        self.web_response(parsed.path,payload,request)
                        return
                    try:
                        response = open_upstream(request)
                    except urllib.error.HTTPError as error:
                        self.upstream_error(error)
                        return
                    except Exception:
                        self.json_error(502, "upstream_transport_error", "Provider transport failed; completion and charge unknown; not retried")
                        self.record["outcome"] = "transport_error"
                        return
                    with gateway.activity_lock:
                        gateway.active_responses.add(response)
                    if gateway.closing.is_set():
                        gateway.close_response(response)
                        self.record.update(outcome="shutdown_inflight", completion="unknown")
                        return
                    with response:
                        self.record["http_status"] = response.status
                        content_type = response.headers.get("Content-Type", "application/json")
                        observer = UsageObserver(content_type.startswith("text/event-stream"))
                        self.send_response(response.status)
                        self.send_header("Content-Type", "text/event-stream" if observer.streaming else "application/json")
                        self.safe_headers(response.headers)
                        self.send_header("Connection", "close")
                        self.end_headers()
                        pending = b""
                        secret = gateway.key.encode()
                        while chunk := response.read1(65536):
                            observer.feed(chunk)
                            pending = (pending + chunk).replace(secret, b"[REDACTED]")
                            keep = len(secret) - 1
                            if len(pending) > keep:
                                cut = len(pending) - keep
                                self.wfile.write(pending[:cut])
                                self.wfile.flush()
                                pending = pending[cut:]
                        self.wfile.write(pending.replace(secret, b"[REDACTED]"))
                        self.wfile.flush()
                        self.record["outcome"] = "response_complete"
                except (BrokenPipeError, ConnectionResetError):
                    self.record.update(outcome="client_disconnected", completion="unknown")
                except (OSError, TimeoutError):
                    self.record.update(outcome="transport_interrupted", completion="unknown")
                except Exception as error:
                    self.record.update(outcome="gateway_error", error_type=type(error).__name__, completion="unknown")
                finally:
                    if response is not None:
                        with gateway.activity_lock:
                            gateway.active_responses.discard(response)
                    if observer is not None:
                        observer.finish()
                        self.record["usage"] = observer.usage or None
                        self.record["usage_status"] = ("observed" if self.record["outcome"] == "response_complete" else "partial") if observer.usage else "unknown"
                        if observer.response_id:
                            self.record["provider_response_id"] = gateway.redact(observer.response_id)
                    self.record["finished_at"] = now()
                    gateway.settle_web(self.record)
                    gateway.receipt(dict(self.record, event="finished"))

            def web_response(self,route,payload,request):
                self.record['web_backend']='local-clash-unix' if route.endswith('/fetch') else 'deepseek'
                self.record.update(web_success=None,estimated_cost_usd=None,
                    cost_status='unknown',cost_source=web_policy.PRICE_SOURCE)
                if self.record['web_backend']=='local-clash-unix':
                    self.record.update(estimated_cost_usd=0,cost_status='no paid fetch provider')
                    def opened(connection):
                        with gateway.activity_lock:
                            if gateway.closing.is_set():raise web_fetch.FetchCancelled('Gateway closing')
                            gateway.active_responses.add(connection)
                    def closed(connection):
                        with gateway.activity_lock:gateway.active_responses.discard(connection)
                    try:value=web_fetch.fetch(payload['url'],cancel=gateway.closing,on_open=opened,on_close=closed)
                    except Exception as error:
                        # A host GET has no paid side effect: any exception means no page
                        # was delivered (including HTTP framing errors such as IncompleteRead).
                        self.record['fetch_error_type']=type(error).__name__
                        reason=web_fetch.failure_reason(error)
                        self.record['fetch_failure_reason']=reason
                        stage=getattr(error,'stage',None)
                        if stage in {'dns_socket_check','dns_bridge_connect','dns_bridge_reply',
                                'clash_dns_connect','clash_dns_http','clash_dns_decode','clash_dns_query',
                                'fetch_socket_check','fetch_tunnel_connect'}:
                            self.record['fetch_failure_stage']=stage
                        if isinstance(error,web_fetch.FetchFailure):self.record['target_http_status']=error.http_status
                        if isinstance(error,web_fetch.ProxyUnavailable):self.record['web_proxy_unavailable']=True
                        self.record['web_success']=False
                        self.json_error(502,'host_fetch_failed','Fetch failed: '+reason+'; no automatic retry')
                        return
                    self.record['web_success']=True
                    self.record.update(http_status=200,outcome='response_complete')
                else:
                    response=None
                    try:
                        response=open_upstream(request)
                        with gateway.activity_lock:
                            gateway.active_responses.add(response)
                        if gateway.closing.is_set():
                            gateway.close_response(response)
                            raise OSError('Gateway closing')
                        with response:
                            self.record['http_status']=response.status
                            if response.status!=200:raise ValueError('Unexpected web status')
                            raw=response.read(2*1024*1024+1)
                            if len(raw)>2*1024*1024:raise ValueError('Oversized web response')
                            value=json.loads(raw)
                            if not isinstance(value,dict):raise ValueError('Invalid web response')
                            if not isinstance(value.get('results'),list):raise ValueError('Invalid search response')
                            success=bool(value['results'])
                            self.record.update(web_success=success,outcome='response_complete',
                                estimated_cost_usd=web_policy.WEB_PRICE_USD if success else 0,
                                cost_status='documented per-success estimate; not an invoice')
                    except urllib.error.HTTPError as error:
                        self.record.update(web_success=False,estimated_cost_usd=0,cost_status='documented nonbillable HTTP failure')
                        self.upstream_error(error)
                        return
                    except Exception:
                        self.json_error(502,'web_transport_error','Web response unavailable or incomplete; charge unknown; not retried')
                        self.record['outcome']='transport_error'
                        return
                    finally:
                        if response is not None:
                            with gateway.activity_lock:gateway.active_responses.discard(response)
                budget=gateway.settle_web(self.record)
                if route.endswith('/search'):
                    value=dict(value,results=[item for item in value['results'] if isinstance(item,dict)
                        and web_policy.allowed_url(item.get('url',''))])
                value={**value,'web_budget':budget}
                data=json.dumps(gateway.sanitize(value),ensure_ascii=True).encode()
                self.send_response(200)
                self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(data)))
                self.send_header('Connection','close')
                self.end_headers()
                self.wfile.write(data)

            def safe_headers(self, headers):
                for name, value in (headers or {}).items():
                    lower = name.lower()
                    allowed = lower in {"request-id", "x-request-id", "retry-after"} or lower.startswith(("x-ratelimit-", "ratelimit-", "anthropic-ratelimit-"))
                    if allowed and len(value) <= 512 and "\r" not in value and "\n" not in value:
                        self.send_header(name, gateway.redact(value))
                        if lower == 'retry-after' or lower.startswith(('x-ratelimit-', 'ratelimit-', 'anthropic-ratelimit-')):
                            self.record.setdefault('rate_limit_headers', {})[lower] = gateway.redact(value)
                        if lower in {"request-id", "x-request-id"} and re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", value):
                            self.record["provider_request_id"] = gateway.redact(value)

            def upstream_error(self, error):
                try:
                    raw = error.read(128 * 1024 + 1)
                    truncated = len(raw) > 128 * 1024
                    raw = raw[:128 * 1024]
                    try:
                        body = json.loads(raw)
                    except (ValueError, UnicodeDecodeError):
                        body = dict(error=dict(type="upstream_error", message=raw.decode("utf-8", errors="replace")))
                    metadata = UsageObserver(False)
                    metadata.observe(body)
                    if not isinstance(body,dict):body=dict(error=dict(type='upstream_error',message='Non-object error response'))
                    if metadata.usage:
                        self.record.update(usage=metadata.usage, usage_status="observed")
                    if self.record.get('web_reserved'):
                        body['web_budget']=gateway.settle_web(self.record)
                    data = json.dumps(gateway.sanitize(body), ensure_ascii=True).encode()
                    self.record.update(http_status=error.code, outcome="upstream_rejected", error_body_truncated=truncated)
                    self.send_response(error.code)
                    self.send_header("Content-Type", "application/json")
                    self.safe_headers(error.headers)
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.wfile.write(data)
                finally:
                    error.close()

        class QuietUnixServer(socketserver.ThreadingUnixStreamServer):
            daemon_threads = True

            def handle_error(self, request, client_address):
                pass

        class QuietHTTPServer(ThreadingHTTPServer):
            def handle_error(self, request, client_address):
                pass

        self.socket_dir = None
        if unix_path is not None and len(os.fsencode(unix_path)) > 100:
            self.socket_dir = tempfile.TemporaryDirectory(prefix="mas-gateway-", dir="/tmp")
            unix_path = Path(self.socket_dir.name) / "gateway.sock"
        self.unix_path = unix_path
        try:
            if unix_path is not None:
                self.server = QuietUnixServer(str(unix_path), Handler)
                os.chmod(unix_path, 0o600)
            else:
                if bind != "127.0.0.1":
                    raise ValueError("TCP gateway must bind to loopback")
                self.server = QuietHTTPServer((bind, 0), Handler)
        except BaseException:
            if self.ledger_fd is not None:
                os.close(self.ledger_fd)
                self.ledger_fd = None
            if self.socket_dir is not None:
                self.socket_dir.cleanup()
            raise
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def redact(self, text):
        return text.replace(self.key, "[REDACTED]").replace(self.token, "[REDACTED]")

    def sanitize(self, value):
        if isinstance(value, str):
            return self.redact(value)
        if isinstance(value, list):
            return [self.sanitize(item) for item in value]
        if isinstance(value, dict):
            sensitive = {"authorization", "x-api-key", "api_key", "apikey", "key", "token", "access_token", "headers"}
            return {self.redact(str(name)): "[REDACTED]" if str(name).lower() in sensitive else self.sanitize(item)
                    for name, item in value.items()}
        return value

    def receipt(self, row):
        data = (json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n").encode()
        with self.ledger_lock:
            if self.ledger_closed:
                return
            self.request_records[row["request_id"]] = dict(row)
            if self.ledger_path is None:
                return
            fd = self.ledger_fd
            self.append_receipt(fd, data)

    @staticmethod
    def append_receipt(fd, data):
        offset = 0
        while offset < len(data):
            offset += os.write(fd, data[offset:])
        os.fsync(fd)

    @staticmethod
    def close_response(response):
        upstream_socket = getattr(getattr(getattr(response, "fp", None), "raw", None), "_sock", None)
        if upstream_socket is None:upstream_socket=getattr(response,'sock',None)
        if upstream_socket is not None:
            try:
                upstream_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        close = getattr(response, "close", None)
        if close is not None:
            try:
                close()
            except OSError:
                pass

    def summary(self):
        with self.ledger_lock:
            rows = list(self.request_records.values())
        return dict(ledger_path=str(self.ledger_path) if self.ledger_path else None,
            requests_received=len(rows), upstream_attempts=sum(r["upstream_attempted"] for r in rows),
            requests_finished=sum(r["event"] == "finished" for r in rows),
            requests_closed_at_shutdown=sum(r["event"] == "shutdown" for r in rows),
            responses_complete=sum(r["outcome"] == "response_complete" for r in rows),
            upstream_rejections=sum(r["outcome"] == "upstream_rejected" for r in rows),
            local_rejections=sum(r["outcome"] == "rejected" and not r["upstream_attempted"] for r in rows),
            unknown_completions=sum(r["upstream_attempted"] and r["outcome"] not in {"response_complete", "upstream_rejected"} for r in rows),
            usage_observed=sum(r.get("usage_status") == "observed" for r in rows),
            web_reservations=self.web_calls, web_limit=self.web_limit,
            web_attempts=self.web_attempts,web_attempt_limit=self.web_attempt_limit,
            model_origin="unverified; native CLI, child and direct tool requests are not distinguished",
            charge_status="unknown; usage and request receipts are not provider invoices",
            reservation_semantics="Successful calls and uncertain completions consume reservations; known failures release them; total attempts bounded")

    def settle_web(self,record):
        with self.lock:
            if record.get('web_reserved') and not record.get('web_settled') and not self.closing.is_set():
                known_failure=record.get('web_success') is False or not record.get('upstream_attempted')
                if known_failure:
                    self.web_calls-=1
                    record['web_refunded']=True
                record['web_settled']=True
            return dict(used=self.web_calls,limit=self.web_limit,remaining=max(0,self.web_limit-self.web_calls),
                attempts=self.web_attempts,attempt_limit=self.web_attempt_limit,
                scope='whole run, shared by every agent and process')

    @property
    def url(self):
        if self.unix_path is not None:
            return "http://127.0.0.1:8765"
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        with self.activity_lock:
            self.closing.set()
            clients = list(self.active_clients)
            responses = list(self.active_responses)
        for client in clients:
            try:
                client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        for response in responses:
            self.close_response(response)
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        if self.unix_path is not None:
            self.unix_path.unlink(missing_ok=True)
        if self.socket_dir is not None:
            self.socket_dir.cleanup()
        with self.ledger_lock:
            for identity, row in list(self.request_records.items()):
                if row["event"] != "finished":
                    terminal = dict(row, event="shutdown", finished_at=now(), outcome="shutdown_inflight" if row["upstream_attempted"] else "shutdown_before_dispatch", completion="unknown" if row["upstream_attempted"] else "not_dispatched")
                    self.request_records[identity] = terminal
                    if self.ledger_fd is not None:
                        self.append_receipt(self.ledger_fd, (json.dumps(terminal, separators=(",", ":")) + "\n").encode())
            self.ledger_closed = True
            if self.ledger_fd is not None:
                os.close(self.ledger_fd)
                self.ledger_fd = None
