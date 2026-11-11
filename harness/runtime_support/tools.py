"""Shared harness SQLite and explicit web tools; no model client."""

import argparse
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import urllib.parse

BUDGET_SCOPE = "whole run, shared by every agent and process"
# Mounted alone in solver containers, so it cannot import web_policy. Must exceed
# the host fetch deadline (web_policy.CLIENT_TIMEOUT_SECONDS; checked by tests).
CLIENT_TIMEOUT_SECONDS = 45


class WebBudgetExhausted(RuntimeError):
    """The run-wide web request budget is used up; this is final for the run."""


def budget_exhausted(limit=None):
    count = f"all {limit} web requests" if limit else "all web requests"
    return WebBudgetExhausted(
        f"Web request budget exhausted: {count} for this run have been used (the limit is shared by every agent "
        "and process). No request was sent. No further web access is possible in this run, and other network "
        "access is disabled; do not retry or try to work around this. Continue with the evidence you already have.")


def configured_limit():
    try:
        return int(os.environ.get("MAS_WEB_MAX_REQUESTS", "20"))
    except ValueError:
        return None


def with_budget(value, budget):
    # Put the budget first so it stays visible when long output is truncated to a preview.
    if isinstance(value, dict):
        return {"web_budget": budget, **{k: v for k, v in value.items() if k != "web_budget"}}
    return {"web_budget": budget, "response": value}


def json_post(url, payload, key):
    config = ("header = " + json.dumps("Authorization: Bearer " + key) + "\n"
              'header = "Content-Type: application/json"\n'
              "data = " + json.dumps(json.dumps(payload)) + "\n")
    result = subprocess.run(["curl", "--silent", "--show-error", "--max-time", str(CLIENT_TIMEOUT_SECONDS),
                             "--max-filesize", "2097152", "--write-out", "\n%{http_code}", "--config", "-", url],
                            input=config, text=True, capture_output=True, timeout=CLIENT_TIMEOUT_SECONDS + 5)
    if result.returncode:
        raise RuntimeError("Web API transport failed (curl exit " + str(result.returncode) + "); not retried")
    body, separator, code = result.stdout.rpartition("\n")
    if not separator or not code.isdigit():
        raise RuntimeError("Web API returned no HTTP status; not retried")
    status = int(code)
    if not 200 <= status < 300:
        try:
            document=json.loads(body)
            error = document.get("error", {})
        except (ValueError, AttributeError):
            document,error = {},{}
        kind = error.get("type") if isinstance(error, dict) else None
        if status == 429 and kind == "run_web_limit_exhausted":
            raise budget_exhausted(configured_limit())
        if status == 429:
            raise RuntimeError("Web provider rate limit (HTTP 429); not retried")
        budget=document.get('web_budget')
        remaining=budget.get('remaining') if isinstance(budget,dict) else None
        suffix='; remaining successful web calls: '+str(remaining) if isinstance(remaining,int) else ''
        if kind=='host_fetch_failed':
            reason=document.get('fetch_failure_reason')
            if isinstance(reason,str) and reason.isascii() and reason.isidentifier() and len(reason)<60:
                suffix+='; reason: '+reason
            target=document.get('target_http_status')
            if type(target) is int and 100<=target<=599:suffix+='; target HTTP '+str(target)
        raise RuntimeError("Web API rejected request (HTTP " + str(status) + "); not retried"+suffix)
    return json.loads(body)


def deepseek_web(action, value):
    if action == "search":
        if not value.strip() or len(value) > 128:
            raise ValueError("DeepSeek search queries must contain 1-128 characters")
        payload = dict(query=value, count=10, need_content=True)
    elif action == "fetch":
        url = urllib.parse.urlsplit(value)
        if len(value) > 8192 or url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
            raise ValueError("DeepSeek fetch requires a public HTTP(S) URL without credentials")
        payload = dict(url=value)
    else:
        raise ValueError("Unsupported DeepSeek web action")
    base = os.environ.get("MAS_WEB_BASE_URL", "").rstrip("/")
    if urllib.parse.urlsplit(base).hostname!='127.0.0.1':
        raise ValueError('DeepSeek web tools require the host credential gateway')
    key = os.environ["ANTHROPIC_AUTH_TOKEN"]
    result=json_post(base + "/v1/tools/" + action, payload, key)
    if not isinstance(result,dict) or not isinstance(result.get('web_budget'),dict):
        raise ValueError('Missing authoritative host web budget')
    return with_budget(result,result['web_budget'])


def share_root():
    """Shared web artifacts live in the solver workspace whatever the caller's cwd."""
    workspace=Path('/workspace')
    return workspace/'web' if workspace.is_dir() and os.access(workspace,os.W_OK) else Path.cwd()/'web'


def save_web(action,value):
    root=share_root()
    root.mkdir(exist_ok=True,mode=0o700)
    directory=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for number in range(1,10001):
            name=f'{action}-{number}.json'
            try:fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
            except FileExistsError:continue
            with os.fdopen(fd,'w') as stream:
                json.dump(value,stream,ensure_ascii=False,indent=2)
            return str(root/name)
        raise ValueError('Too many local web artifacts')
    finally:os.close(directory)


def print_web(action,value):
    # The web call has already completed and may be charged: a local file
    # problem must not discard the result before it reaches stdout.
    header=dict(web_budget=value['web_budget'])
    try:header['full_result_file']=save_web(action,value)
    except (OSError,ValueError) as error:
        header.update(full_result_file=None,full_result_file_error=type(error).__name__)
    print(json.dumps(header,ensure_ascii=False))
    if action=='search':
        for item in value.get('results',[])[:10]:
            if not isinstance(item,dict):continue
            text=item.get('summary') or item.get('snippet') or item.get('content') or ''
            row=dict(title=str(item.get('title',''))[:200],url=str(item.get('url',''))[:1000],
                site=str(item.get('site_name') or '')[:100],excerpt=str(text)[:1500])
            while len(json.dumps(row,ensure_ascii=False).encode())>2200 and row['excerpt']:
                row['excerpt']=row['excerpt'][:int(len(row['excerpt'])*.8)]
            print(json.dumps(row,ensure_ascii=False))
    else:
        text=str(value.get('content',''))[:20000]
        while len(text.encode())>22000:text=text[:int(len(text)*.9)]
        print(text)


def run_sql(path, sql, *, limit=200, operations=None):
    if operations is not None and (type(operations) is not int or operations <= 0):
        raise ValueError('SQL operation limit must be a positive integer')
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
        if operations is not None:
            connection.set_progress_handler(progress, 1000)
        try:
            cursor = connection.execute(sql)
            rows = cursor.fetchmany(limit + 1)
        except sqlite3.OperationalError as error:
            if operations is not None and remaining <= 0:
                raise sqlite3.OperationalError(
                    f'SQL operation limit ({operations}) exceeded; increase --operations or omit it. '
                    'The solver wall-clock deadline still applies.') from error
            raise
        return dict(columns=[col[0] for col in cursor.description or ()], rows=rows[:limit], truncated=len(rows) > limit)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="tool", required=True)
    sql = sub.add_parser("sql")
    sql.add_argument("--db", required=True, type=Path)
    sql.add_argument("--query", required=True)
    sql.add_argument("--operations", type=int, help="Optional SQLite VM operation limit; no default cap")
    search = sub.add_parser("search")
    search.add_argument("--query", required=True)
    fetch = sub.add_parser("fetch")
    fetch.add_argument("--url", required=True)
    args = parser.parse_args(argv)
    try:
        return run_tool(args)
    except WebBudgetExhausted as error:
        # One clear, final message instead of a traceback; exit status 3 means no budget left.
        print(error, file=sys.stderr)
        return 3
    except sqlite3.Error as error:
        print(json.dumps(dict(error=type(error).__name__,message=str(error)[:500])),file=sys.stderr)
        return 2
    except (RuntimeError,ValueError) as error:
        print(str(error),file=sys.stderr)
        return 2


def run_tool(args):
    if args.tool == "sql":
        value = run_sql(args.db, args.query, operations=args.operations)
    else:
        if os.environ.get("MAS_BENCHMARK_WEB") != "1":
            raise ValueError("Web access is not enabled for this task")
        if os.environ.get("MAS_WEB_PROVIDER")!='deepseek':
            raise ValueError("Unknown web provider")
        value = deepseek_web(args.tool, args.query if args.tool == "search" else args.url)
        print_web(args.tool,value)
        return 0
    print(json.dumps(value, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
