"""Benchmark-independent batch execution.

Every run gets a fresh trace; earlier attempts stay under ``traces/attempts``.
Finished results are never rerun. Provider failures are written with status
``error`` and rerun by the next invocation, never scored as wrong answers. A
request that exceeds the model's context cannot succeed on rerun, so it ends
the run as ``incomplete``. Key or balance failures stop the whole batch.
"""

from __future__ import annotations

import functools
import hashlib
import json
import re
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from . import accounting
from .config import digest, source_digest
from .llm import ModelConfig, ProviderError
from .trace import Trace, read_trace, tool_counts, usage_summary


def bounded_jobs(items, worker, concurrency, stop_on, stop_event=None):
    """Dispatch only an active window; stop new work and drain in-flight jobs."""
    if concurrency < 1:
        raise ValueError('Concurrency must be positive')
    stop = stop_event if stop_event is not None else threading.Event()
    iterator = iter(items)
    def guarded(item):
        try:
            result = worker(item)
        except BaseException:
            stop.set()
            raise
        if stop_on(result):
            stop.set()
        return result
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        pending = set()
        exhausted = False
        while pending or not exhausted:
            while not stop.is_set() and not exhausted and len(pending) < concurrency:
                try:
                    item = next(iterator)
                except StopIteration:
                    exhausted = True
                    break
                pending.add(pool.submit(guarded, item))
            if not pending:
                break
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                yield future.result()


@dataclass(frozen=True)
class RunSpec:
    benchmark: str
    task_id: str
    condition: str
    repeat: int

    @property
    def run_id(self) -> str:
        task = re.sub(r"[^A-Za-z0-9]+", "-", self.task_id).strip("-")
        if task != self.task_id or len(task) > 48:
            task = f"{task[:40]}-{hashlib.sha1(self.task_id.encode()).hexdigest()[:6]}"
        return f"{self.benchmark}_q{task}_{self.condition}_r{self.repeat}"


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def append_jsonl(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(value, ensure_ascii=False) + "\n")


@functools.cache
def _source() -> str:
    return source_digest()


def prepare_output(out: Path, frozen: dict, info: dict | None = None) -> None:
    """Create or reopen an output directory; refuse a different frozen setup."""
    path = out / "manifest.json"
    key = digest(frozen)
    if path.exists():
        recorded = json.loads(path.read_text())["frozen_digest"]
        if recorded != key:
            raise RuntimeError(f"{out} was created with another frozen setup; use a new directory")
        return
    out.mkdir(parents=True, exist_ok=True)
    write_json(
        path,
        {
            "frozen": frozen,
            "frozen_digest": key,
            "source_digest": _source(),
            "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            **(info or {}),
        },
    )


def record_balance(out: Path, cfg: ModelConfig, when: str) -> None:
    """Append the account balance; the start/end difference is the actual charge."""
    try:
        append_jsonl(out / "balance.jsonl", {"when": when, **accounting.balance(cfg)})
    except Exception as error:  # accounting must never stop a batch
        print(f"balance check failed: {error!r}", flush=True)


def result_path(out: Path, spec: RunSpec) -> Path:
    return out / "results" / f"{spec.run_id}.json"


def finished(out: Path, spec: RunSpec) -> bool:
    path = result_path(out, spec)
    return path.exists() and json.loads(path.read_text())["status"] != "error"


def _failure(error: ProviderError) -> dict:
    record = {
        "kind": error.kind,
        "http_status": error.status,
        "fatal": error.fatal,
        "message": str(error)[:4000],
    }
    if error.kind == "context_length":
        return {"status": "incomplete", "reason": "context_length", "error": record}
    return {"status": "error", "error": record}


def run_one(
    spec: RunSpec,
    execute: Callable[[RunSpec, Trace], dict],
    out: Path,
    pricing: dict | None = None,
) -> dict:
    trace_path = out / "traces" / f"{spec.run_id}.jsonl"
    if trace_path.exists():
        attempts = trace_path.parent / "attempts"
        attempts.mkdir(parents=True, exist_ok=True)
        number = len(list(attempts.glob(f"{spec.run_id}.*.jsonl")))
        trace_path.rename(attempts / f"{spec.run_id}.{number}.jsonl")
    start = time.monotonic()
    with Trace(trace_path, spec.run_id) as trace:
        trace.emit("run_start", **asdict(spec))
        try:
            result = execute(spec, trace)
        except ProviderError as error:
            result = _failure(error)
        except Exception as error:
            result = {
                "status": "error",
                "error": {
                    "kind": type(error).__name__,
                    "message": str(error)[:4000],
                    "traceback": traceback.format_exc()[-8000:],
                },
            }
        if "error" in result:
            trace.emit("error", **result["error"])
        trace.emit("run_end", status=result["status"])
    events = read_trace(trace_path)
    result = {
        "run_id": spec.run_id,
        **asdict(spec),
        **result,
        "usage": usage_summary(events),
        "tool_call_counts": tool_counts(events),
        "cost_usd_estimate": accounting.estimate(events, pricing) if pricing else None,
        "wall_seconds": round(time.monotonic() - start, 2),
        "source_digest": _source(),
    }
    write_json(result_path(out, spec), result)
    return result


def progress(result: dict) -> str:
    total = result["usage"]["total"]
    prompt, hit = total["prompt_tokens"], total["cache_hit_tokens"]
    rate = f"{hit / prompt:.0%}" if prompt else "-"
    cost = result.get("cost_usd_estimate")
    money = f"${cost:.4f}" if cost is not None else "$?"
    return (
        f"{result['run_id']}: {result['status']} | prompt {prompt} (cache hit {rate}) "
        f"| output {total['completion_tokens']} | {money} | {result['wall_seconds']}s"
    )


def run_batch(
    specs: list[RunSpec],
    execute: Callable[[RunSpec, Trace], dict],
    out: Path,
    concurrency: int,
    pricing: dict | None = None,
) -> dict[str, int]:
    """Run every unfinished spec; returns a count of result statuses."""
    pending = [spec for spec in specs if not finished(out, spec)]
    print(f"{len(specs) - len(pending)} finished, {len(pending)} to run", flush=True)
    stop = threading.Event()

    def guarded(spec: RunSpec) -> dict | None:
        if stop.is_set():
            return None
        result = run_one(spec, execute, out, pricing)
        if result.get("error", {}).get("fatal"):
            stop.set()
        return result

    statuses: dict[str, int] = {}
    with ThreadPoolExecutor(max(1, concurrency)) as pool:
        futures = [pool.submit(guarded, spec) for spec in pending]
        for done, future in enumerate(as_completed(futures), start=1):
            result = future.result()
            status = result["status"] if result else "skipped"
            statuses[status] = statuses.get(status, 0) + 1
            if result:
                print(f"[{done}/{len(pending)}] {progress(result)}", flush=True)
    if stop.is_set():
        print("Stopped early: the provider rejected the key, balance or permission.", flush=True)
    return statuses
