"""Explicit FDABench asset preparation, with pinned sources and no model calls."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import http.client
import ipaddress
from functools import wraps
import json
import os
from pathlib import Path
import re
import shutil
import socket
import sqlite3
import sys
import threading
import time
import urllib.parse
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from benchmarks._external import digest, asset_manifest
from benchmarks.fdabench.tasks import DATASET, DATA_REVISION, load_tasks, database_path
from common.io import write_json
from harness.runtime_support.web_fetch import proxy_connection, check_proxy

HF_ENDPOINT = "https://hf-mirror.com"

CORPUS = ("FDAbench2026/FDABench-File", "9c88acf42f37a65c6aef8d06e1f6b6a1c24b7ca5")
# BIRD/Spider1 mirrors contain database files, not solver/task releases. Receipts
# retain their mirror provenance; do not claim an independently verified original.
BIRD = ("prem-research/birdbench", "4d033eb86e648b20a6cad11fe1c51b46cc0e185d")
SPIDER1 = ("HAL-9001/spider-databases", "4a01bbac6520cd35b216db9e1724e5e1ada60aa4")
SPIDER2 = ("xlangai/spider2-localdb", "c700cf8fe4064c745274870ba1c295f33610736a")
SPIDER2_COMPLETE = dict(
    filename="local_sqlite.zip", bytes=456643204,
    sha256="d56acf7c9d89be4bdf1f4f1281f4a03d91735f1858f6d6d0cfe0f9d562e3a94f",
    source_url="https://drive.usercontent.google.com/download?id=1coEVsCZq-Xvj9p2TnhBFoFTsY-UoYGmG&export=download&confirm=t",
    source_reference="https://github.com/xlang-ai/Spider2/blob/cafb867313aab4e674652054198f383cf4018943/spider2-lite/README.md",
    published_upstream_checksum=False,
)
TRANSFER_SLOTS = threading.BoundedSemaphore(4)
HF_TOKEN = None
DNS_CHECKS = {}
DNS_LOCK = threading.Lock()
CONNECTIONS = threading.local()
ASSET_TIMEOUT = 20
CDN_PROXY_SOCKET = None
WORKING_ADDRESSES = {}


def asset_socket(address, timeout=ASSET_TIMEOUT, source_address=None):
    """Bound the entire address list, not timeout seconds for each CDN address."""
    host, port = address
    addresses = list(dict.fromkeys(row[4][0] for row in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)))
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
        raise ValueError('Asset host resolved to a non-public address')
    previous = WORKING_ADDRESSES.get(host)
    if previous and previous[0] in addresses and time.monotonic() - previous[1] < 60:
        addresses.remove(previous[0])
        addresses.insert(0, previous[0])
    deadline = time.monotonic() + timeout
    for ip in addresses:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            connection = socket.create_connection((ip, port), timeout=min(2, remaining), source_address=source_address)
        except OSError:
            continue
        connection.settimeout(timeout)
        WORKING_ADDRESSES[host] = ip, time.monotonic()
        return connection
    raise TimeoutError('Asset address-list connection deadline exceeded')


def transport():
    return 'mirror-direct-cdn-mac-clash' if CDN_PROXY_SOCKET else 'server-direct-https'


def use_cdn_proxy(host):
    return CDN_PROXY_SOCKET is not None and host.endswith(('.hf.co', '.huggingface.co', '.hf-mirror.com'))


class ConnectionLease:
    """Return fully consumed keep-alive connections to a thread-local pool."""
    def __init__(self, host):
        self.host = host
        self.key = (host, str(CDN_PROXY_SOCKET) if use_cdn_proxy(host) else None)
        pool = getattr(CONNECTIONS, 'pool', None)
        if pool is None:
            pool = CONNECTIONS.pool = {}
        self.pool = pool
        previous = pool.pop(self.key, None)
        self.connection = None
        if previous:
            connection, saved = previous
            if time.monotonic() - saved < 15:
                self.connection = connection
            else:
                connection.close()
        if self.connection is None:
            if use_cdn_proxy(host):
                self.connection = proxy_connection(host, 443, True, ASSET_TIMEOUT, CDN_PROXY_SOCKET)
                self.connection.set_tunnel(host, 443)
            else:
                self.connection = http.client.HTTPSConnection(host, 443, timeout=ASSET_TIMEOUT)
                self.connection._create_connection = asset_socket
        self.result = None

    def request(self, *args, **kwargs):
        self.connection.request(*args, **kwargs)

    def getresponse(self):
        self.result = self.connection.getresponse()
        return self.result

    def close(self, *, discard=False):
        connection, self.connection = self.connection, None
        if connection is None:
            return
        if (not discard and self.result is not None and
                getattr(self.result, 'isclosed', lambda: False)() and
                not getattr(self.result, 'will_close', True) and
                getattr(self.result, 'length', None) in (None, 0)):
            previous = self.pool.pop(self.key, None)
            if previous:
                previous[0].close()
            self.pool[self.key] = connection, time.monotonic()
        else:
            connection.close()


def parallel_items(operation, items, workers):
    executor = ThreadPoolExecutor(max_workers=workers)
    pending = [executor.submit(operation, item) for item in items]
    try:
        for future in as_completed(pending):
            yield future.result()
    finally:
        # Do not run the entire remaining queue after a fatal/auth/integrity error.
        executor.shutdown(wait=True, cancel_futures=True)


def validate_download_host(host):
    # Bound repeat DNS checks for the same allowlisted host during bulk transfer.
    with DNS_LOCK:
        checked = DNS_CHECKS.get(host)
        if checked is None or time.monotonic() - checked >= 120:
            addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
                raise ValueError("Asset host resolved to a non-public address")
            DNS_CHECKS[host] = time.monotonic()


def auth_headers(host, target):
    # User-authorized mirror authentication is restricted to the gated corpus.
    paths = tuple(f"{prefix}/{CORPUS[0]}/" for prefix in ("/datasets", "/api/datasets"))
    if host in {"huggingface.co", "hf-mirror.com"} and target.startswith(paths) and HF_TOKEN:
        return {"Authorization": "Bearer " + HF_TOKEN}
    return {}


def retry_transfer(operation):
    """Only public asset I/O is retried; never a model/judge invocation."""
    @wraps(operation)
    def bounded(*args, **kwargs):
        for attempt in range(5):
            try:
                return operation(*args, **kwargs)
            except (OSError, http.client.IncompleteRead, http.client.RemoteDisconnected) as error:
                if attempt == 4:
                    raise
                print(json.dumps(dict(asset_retry=attempt + 1, error_type=type(error).__name__,
                                      wait_seconds=2 ** (attempt + 1))), flush=True)
                time.sleep(2 ** (attempt + 1))
    return bounded


def response(url, *, byte_range=None):
    """Mirror-direct HTTPS, with a run-specific opt-in private CDN tunnel."""
    for _ in range(8):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443):
            raise ValueError("Unsafe download URL")
        host = parsed.hostname
        if not (host in {"hf-mirror.com", "huggingface.co"} or
                host and host.endswith((".hf-mirror.com", ".huggingface.co", ".hf.co"))):
            raise ValueError("Unexpected asset download host")
        validate_download_host(host)
        connection = ConnectionLease(host)
        started = time.monotonic()
        try:
            target = urllib.parse.urlunsplit(("", "", parsed.path, parsed.query, ""))
            headers = {"Accept-Encoding": "identity", "User-Agent": "MAS-asset-preparation/1"}
            headers.update(auth_headers(host, parsed.path))
            if byte_range is not None:
                headers["Range"] = f"bytes={byte_range[0]}-{byte_range[1]}"
            connection.request("GET", target, headers=headers)
            result = connection.getresponse()
            if result.status in {301, 302, 303, 307, 308}:
                url = urllib.parse.urljoin(url, result.getheader("Location", ""))
                if result.getheader('Content-Length', '').isdigit() and int(result.getheader('Content-Length')) <= 65536:
                    result.read()
                connection.close()
                continue
            if result.status != (206 if byte_range else 200):
                raise RuntimeError(f"Asset HTTP {result.status}; no retry")
            return connection, result
        except BaseException as error:
            connection.close(discard=True)
            print(json.dumps(dict(asset_host=host, error_type=type(error).__name__,
                                  seconds=round(time.monotonic() - started, 2))), flush=True)
            raise
    raise ValueError("Too many asset redirects")


@retry_transfer
def download_blob(url, destination, size):
    """Bounded ranges avoid one multi-GB asset serializing all preparation."""
    if size < 64 * 1024 * 1024:
        if destination.is_symlink():
            raise ValueError("Partial asset must not be a symlink")
        start = destination.stat().st_size if destination.is_file() else 0
        if start > size:
            raise ValueError("Partial asset exceeds expected size")
        if start == size and destination.is_file():
            return
        with TRANSFER_SLOTS:
            connection, result = response(url, byte_range=(start, size - 1) if start else None)
            try:
                if start and result.getheader('Content-Range') != f'bytes {start}-{size - 1}/{size}':
                    raise ValueError("Asset server returned a different byte range")
                with destination.open("ab" if start else "wb") as stream:
                    # Persist received bytes even if a later read stalls or disconnects.
                    while block := result.read1(256 * 1024):
                        stream.write(block)
            finally:
                connection.close()
        if destination.stat().st_size != size:
            raise OSError("Incomplete asset transfer")
        return
    parts = destination.with_name(destination.name + ".ranges")
    if parts.is_symlink():
        raise ValueError("Asset range directory must not be a symlink")
    parts.mkdir(exist_ok=True)
    chunk = 16 * 1024 * 1024
    def segment(start):
        end = min(size, start + chunk) - 1
        path = parts / str(start)
        if path.is_file() and not path.is_symlink() and path.stat().st_size == end - start + 1:
            return path
        with TRANSFER_SLOTS:
            connection, result = response(url, byte_range=(start, end))
            try:
                if result.getheader("Content-Range") != f"bytes {start}-{end}/{size}":
                    raise ValueError("Asset server returned a different byte range")
                temporary = path.with_suffix(".part")
                with temporary.open("wb") as stream:
                    shutil.copyfileobj(result, stream, 1024 * 1024)
                if temporary.stat().st_size != end - start + 1:
                    raise OSError("Incomplete asset range")
                temporary.replace(path)
            finally:
                connection.close()
        return path
    with ThreadPoolExecutor(max_workers=4) as executor:
        files = list(executor.map(segment, range(0, size, chunk)))
    with destination.open("wb") as output:
        for path in files:
            with path.open("rb") as source:
                shutil.copyfileobj(source, output, 1024 * 1024)


@retry_transfer
def inventory(repository, revision, endpoint=HF_ENDPOINT):
    url = f"{endpoint}/api/datasets/{repository}/tree/{revision}?recursive=true&limit=1000"
    files, visited = [], set()
    while url:
        if url in visited:
            raise ValueError("Repeated asset inventory page")
        visited.add(url)
        connection, result = response(url)
        try:
            rows = json.load(result)
            files.extend(r for r in rows if r["type"] == "file")
            link = result.getheader("Link", "")
            match = re.search(r'<([^>]+)>;\s*rel="next"', link)
            url = match.group(1) if match else None
        finally:
            connection.close()
    if len({r["path"] for r in files}) != len(files):
        raise ValueError("Duplicate asset inventory paths")
    return files


def fetch(repository, revision, item, destination, endpoint=HF_ENDPOINT):
    destination = Path(destination)
    relative = item["path"]
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("Unsafe asset path")
    def valid(path):
        if path.is_symlink() or not path.is_file() or path.stat().st_size != item["size"]:
            return False
        if item.get("lfs"):
            return digest(path) == item["lfs"]["oid"]
        value = hashlib.sha1(f"blob {item['size']}\0".encode())
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                value.update(block)
        return value.hexdigest() == item["oid"]
    reused = valid(destination)
    if not reused:
        if destination.exists() or destination.is_symlink():
            raise ValueError("Existing asset differs; refusing overwrite: " + str(destination))
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_name(destination.name + ".part")
        url = f"{endpoint}/datasets/{repository}/resolve/{revision}/{urllib.parse.quote(relative)}"
        download_blob(url, partial, item["size"])
        if not valid(partial):
            raise ValueError("Asset failed integrity check: " + relative)
        partial.replace(destination)
        ranges = partial.with_name(partial.name + ".ranges")
        if ranges.is_dir():
            shutil.rmtree(ranges)
    return dict(repository=repository, revision=revision, path=relative,
                bytes=item["size"], sha256=digest(destination), endpoint=endpoint,
                transport=transport(), reused_verified=reused)


def extract_databases(archive, tasks, data, family):
    receipts = {}
    with zipfile.ZipFile(archive) as bundle:
        for task in tasks:
            if task.reference["database_type"].lower() != family:
                continue
            destination = database_path(task, data)
            if str(destination) in receipts:
                continue
            candidates = [n for n in bundle.namelist() if Path(n).name == task.db + ".sqlite"
                          and "__MACOSX" not in Path(n).parts]
            if family == 'spider1':
                candidates = [n for n in candidates if 'test_database' in Path(n).parts]
            if len(candidates) != 1:
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.is_symlink():
                raise ValueError("Database destination must not be a symlink")
            if not destination.exists():
                partial = destination.with_suffix(".part")
                with bundle.open(candidates[0]) as source, partial.open("xb") as output:
                    shutil.copyfileobj(source, output)
                partial.replace(destination)
            else:
                expected = hashlib.sha256()
                with bundle.open(candidates[0]) as source:
                    for block in iter(lambda: source.read(1024 * 1024), b""):
                        expected.update(block)
                if digest(destination) != expected.hexdigest():
                    raise ValueError("Existing database differs from pinned archive")
            receipts[str(destination)] = dict(archive_sha256=digest(archive), member=candidates[0], sha256=digest(destination))
    return receipts


def supplement_spider2(root, tasks, receipts):
    """Use the separately acquired official pack only for gaps in the HF snapshot."""
    archive = root / "downloads" / SPIDER2_COMPLETE["filename"]
    if not archive.exists() and not archive.is_symlink():
        return {}
    if (archive.is_symlink() or not archive.is_file()
            or archive.stat().st_size != SPIDER2_COMPLETE["bytes"]
            or digest(archive) != SPIDER2_COMPLETE["sha256"]):
        raise ValueError("Complete Spider2 archive differs from its frozen acquisition pin")
    remaining = [task for task in tasks if str(database_path(task, root / "data")) not in receipts]
    extracted = extract_databases(archive, remaining, root / "data", "spider2-lite")
    return {path: {**value, "source": dict(SPIDER2_COMPLETE)} for path, value in extracted.items()}


def main(argv=None):
    global TRANSFER_SLOTS, HF_TOKEN, CDN_PROXY_SOCKET
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="External FDABench directory, not the source checkout")
    parser.add_argument("--assets", nargs="+", choices=("release", "databases", "corpus"), default=["release"])
    parser.add_argument("--workers", type=int, choices=range(1, 9), default=4)
    parser.add_argument("--hf-endpoint", choices=(HF_ENDPOINT, "https://huggingface.co"), default=HF_ENDPOINT)
    parser.add_argument("--cdn-proxy-socket", type=Path, help="Run-authorized private Mac tunnel for CDN hosts only; mirror remains direct")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--hf-credentials", type=Path, help="Host-only mode-0600 dotenv file containing HF_TOKEN")
    args = parser.parse_args(argv)
    CDN_PROXY_SOCKET = args.cdn_proxy_socket
    TRANSFER_SLOTS = threading.BoundedSemaphore(args.workers)
    root = args.root.resolve()
    source = Path(__file__).resolve().parents[2]
    if root.is_relative_to(source) or source.is_relative_to(root):
        raise ValueError("Assets must stay outside source checkout")
    if not args.execute:
        print(json.dumps(dict(status="planned", assets=args.assets, root=str(root),
                              endpoint=args.hf_endpoint, transport=transport(), paid_calls=0)))
        return 0
    if args.hf_credentials:
        from harness.runtime_support.runtime import credential
        HF_TOKEN = credential(args.hf_credentials, 'HF_TOKEN')
    if CDN_PROXY_SOCKET:
        check_proxy(CDN_PROXY_SOCKET)
    os.umask(0o077)
    root.mkdir(parents=True, exist_ok=True)
    if "release" in args.assets:
        items = inventory(DATASET, DATA_REVISION, args.hf_endpoint)
        selected = [r for r in items if r["path"] in {f"{p}/data.jsonl" for p in ("report", "single", "multiple")}]
        if len(selected) != 3:
            raise ValueError("Incomplete release inventory")
        receipt = [fetch(DATASET, DATA_REVISION, r, root / "release" / (r["path"].split('/')[0] + '.jsonl'), args.hf_endpoint)
                   for r in selected]
        write_json(root / "release-receipt.json", dict(files=receipt, paid_calls=0))
    tasks = load_tasks(root / "release")
    data = root / "data"
    if "databases" in args.assets:
        receipts = {}
        repo, revision = BIRD
        names = {t.db for t in tasks if t.reference["database_type"].lower() == "bird"}
        items = [r for r in inventory(repo, revision, args.hf_endpoint)
                 if r["path"] in {f"train/train_databases/{n}/{n}.sqlite" for n in names}]
        def bird(item):
            name = Path(item["path"]).stem
            target = data / "bird" / name / (name + ".sqlite")
            value = fetch(repo, revision, item, target, args.hf_endpoint)
            return str(target), value
        for target, value in parallel_items(bird, items, args.workers):
            receipts[target] = value
            write_json(root / "database-receipt.json", dict(files=receipts, complete=False, paid_calls=0))
        for family, (repo, revision), filename in (("spider1", SPIDER1, "spider_data.zip"),
                                                   ("spider2-lite", SPIDER2, "sqlite.zip")):
            item = next(r for r in inventory(repo, revision, args.hf_endpoint) if r["path"] == filename)
            archive = root / "downloads" / filename
            fetched = fetch(repo, revision, item, archive, args.hf_endpoint)
            extracted = extract_databases(archive, tasks, data, family)
            receipts.update({p: {**v, "source": fetched} for p, v in extracted.items()})
        receipts.update(supplement_spider2(root, tasks, receipts))
        for path in receipts:
            with sqlite3.connect(Path(path).as_uri() + "?mode=ro", uri=True) as db:
                if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise ValueError("SQLite integrity failure")
        missing = sorted({str(database_path(t, data)) for t in tasks if not database_path(t, data).is_file()})
        write_json(root / "database-receipt.json", dict(files=receipts, missing=missing, complete=not missing, paid_calls=0))
    if "corpus" in args.assets:
        repo, revision = CORPUS
        items = [r for r in inventory(repo, revision, args.hf_endpoint)
                 if not Path(r["path"]).name.startswith(".") and r["path"] != "README.md"]
        def document(item):
            return item["path"], fetch(repo, revision, item, data / "corpus" / item["path"], args.hf_endpoint)
        receipts = {}
        started, reported = time.monotonic(), 0
        verified_bytes = downloaded_bytes = downloaded_files = 0
        for relative, value in parallel_items(document, items, args.workers):
            receipts[relative] = value
            verified_bytes += value['bytes']
            if not value['reused_verified']:
                downloaded_bytes += value['bytes']
                downloaded_files += 1
            elapsed = time.monotonic() - started
            if elapsed - reported >= 10 or len(receipts) == len(items):
                progress = dict(corpus_verified=len(receipts), total=len(items), verified_bytes=verified_bytes,
                                newly_completed_files=downloaded_files, newly_completed_bytes=downloaded_bytes,
                                elapsed_seconds=round(elapsed, 1), endpoint=args.hf_endpoint,
                                completed_bytes_per_second=round(downloaded_bytes / max(elapsed, 0.001)))
                write_json(data / 'corpus-download-progress.json', progress)
                print(json.dumps(progress), flush=True)
                reported = elapsed
        write_json(data / "corpus-receipt.json", dict(kind="fdabench-raw-corpus-v1", repository=repo,
                   revision=revision, files=asset_manifest(data / "corpus"), source_files=receipts, paid_calls=0))
    print(json.dumps(dict(status="prepared", assets=args.assets, local_scoreable_tasks=len(tasks), paid_calls=0)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
