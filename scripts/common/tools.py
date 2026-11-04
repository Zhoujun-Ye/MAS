"""Read-only SQLite and explicit DeepSeek/Tavily web tools; no model client."""

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import urllib.parse
import urllib.request


def reserve_search(query, *, provider="tavily", action="search"):
    path = os.environ.get("MAS_WEB_LEDGER")
    limit = int(os.environ.get("MAS_WEB_MAX_REQUESTS", "4"))
    if limit < 1:
        raise ValueError("Search request limit must be positive")
    if not path:
        raise ValueError("Search limit requires a shared ledger")
    with open(path, "a+") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.seek(0)
        rows = [json.loads(line) for line in stream if line.strip()]
        if len(rows) >= limit:
            raise ValueError("Search request budget exhausted; no request sent")
        stream.write(json.dumps(dict(attempt=len(rows) + 1, provider=provider, action=action,
                                    reservation_only=True, completion="unknown",
                                    reserved_credits=1 if provider == "tavily" else None,
                                    reserved_usd=0.00075 if provider == "deepseek" else None,
                                    query_sha256=hashlib.sha256(query.encode()).hexdigest())) + "\n")
        stream.flush()


def tavily_search(query):
    reserve_search(query)
    payload = dict(query=query, max_results=5, search_depth="basic", auto_parameters=False, include_usage=True)
    # stdin keeps credentials out of process arguments and error receipts.
    return json_post("https://api.tavily.com/search", payload, os.environ["TAVILY_API_KEY"])


def json_post(url, payload, key):
    config = ("header = " + json.dumps("Authorization: Bearer " + key) + "\n"
              'header = "Content-Type: application/json"\n'
              "data = " + json.dumps(json.dumps(payload)) + "\n")
    result = subprocess.run(["curl", "--silent", "--show-error", "--max-time", "30",
                             "--max-filesize", "2097152", "--write-out", "\n%{http_code}", "--config", "-", url],
                            input=config, text=True, capture_output=True, timeout=35)
    if result.returncode:
        raise RuntimeError("Web API transport failed (curl exit " + str(result.returncode) + "); not retried")
    body, separator, code = result.stdout.rpartition("\n")
    if not separator or not code.isdigit():
        raise RuntimeError("Web API returned no HTTP status; not retried")
    status = int(code)
    if not 200 <= status < 300:
        try:
            error = json.loads(body).get("error", {})
        except (ValueError, AttributeError):
            error = {}
        kind = error.get("type") if isinstance(error, dict) else None
        if status == 429 and kind == "run_web_limit_exhausted":
            raise RuntimeError("Web request budget exhausted (HTTP 429); no provider request sent; do not retry")
        if status == 429:
            raise RuntimeError("Web provider rate limit (HTTP 429); not retried")
        raise RuntimeError("Web API rejected request (HTTP " + str(status) + "); not retried")
    return json.loads(body)


def deepseek_web(action, value):
    if action == "search":
        if not value.strip() or len(value) > 128:
            raise ValueError("DeepSeek search queries must contain 1-128 characters")
        payload = dict(query=value, count=5, need_content=True)
    elif action == "fetch":
        url = urllib.parse.urlsplit(value)
        if len(value) > 8192 or url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
            raise ValueError("DeepSeek fetch requires a public HTTP(S) URL without credentials")
        payload = dict(url=value)
    else:
        raise ValueError("Unsupported DeepSeek web action")
    key = os.environ.get("DEEPSEEK_API_KEY") or os.environ["ANTHROPIC_AUTH_TOKEN"]
    reserve_search(value, provider="deepseek", action=action)
    return json_post(os.environ.get("MAS_WEB_BASE_URL", "https://api.deepseek.com").rstrip("/") + "/v1/tools/" + action, payload, key)


def run_sql(path, sql, *, limit=200, operations=10000000):
    uri = Path(path).resolve(strict=True).as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=10) as connection:
        connection.execute("PRAGMA query_only=ON")
        denied = {sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH}
        def authorize(action, arg1, arg2, db, source):
            if action in denied or (action == sqlite3.SQLITE_FUNCTION and str(arg2).lower() == "load_extension"):
                return sqlite3.SQLITE_DENY
            if action == sqlite3.SQLITE_PRAGMA and arg2 is not None and str(arg1).lower() not in {"table_info", "table_xinfo", "index_info", "index_list", "foreign_key_list"}:
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        connection.set_authorizer(authorize)
        remaining = operations
        def progress():
            nonlocal remaining
            remaining -= 1000
            return int(remaining <= 0)
        connection.set_progress_handler(progress, 1000)
        cursor = connection.execute(sql)
        rows = cursor.fetchmany(limit + 1)
        return dict(columns=[col[0] for col in cursor.description or ()], rows=rows[:limit], truncated=len(rows) > limit)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="tool", required=True)
    sql = sub.add_parser("sql")
    sql.add_argument("--db", required=True, type=Path)
    sql.add_argument("--query", required=True)
    search = sub.add_parser("search")
    search.add_argument("--query", required=True)
    fetch = sub.add_parser("fetch")
    fetch.add_argument("--url", required=True)
    args = parser.parse_args(argv)
    if args.tool == "sql":
        value = run_sql(args.db, args.query)
    else:
        if os.environ.get("MAS_BENCHMARK_WEB") != "1":
            raise ValueError("Web access is not enabled for this task")
        provider = os.environ.get("MAS_WEB_PROVIDER", "tavily")
        if provider == "deepseek":
            value = deepseek_web(args.tool, args.query if args.tool == "search" else args.url)
            print(json.dumps(value, ensure_ascii=False))
            return
        if provider != "tavily":
            raise ValueError("Unknown web provider")
        if args.tool == "search":
            value = tavily_search(args.query)
            print(json.dumps(value, ensure_ascii=False))
            return
        else:
            if urllib.parse.urlsplit(args.url).scheme not in {"http", "https"}:
                raise ValueError("Web fetch requires HTTP(S)")
            request = urllib.request.Request(args.url, headers={"User-Agent": "MAS-benchmark-research/1.0"})
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read(2 * 1024 * 1024 + 1)
            if len(body) > 2 * 1024 * 1024:
                raise ValueError("Web response exceeds 2 MiB; use a more targeted source")
            value = json.loads(body) if args.tool == "search" else dict(url=response.url, content=body.decode("utf-8", errors="replace"))
    print(json.dumps(value, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
