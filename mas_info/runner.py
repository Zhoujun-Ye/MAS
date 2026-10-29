"""Batch execution shared by both benchmarks.

Every run gets a fresh trace; earlier attempts stay under ``traces/attempts``.
Finished results are never rerun. Provider failures are written with status
``error`` and rerun by the next invocation, never scored as wrong answers.
"""

from __future__ import annotations

import functools
import hashlib
import json
import re
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from .config import digest, source_digest
from .llm import ProviderError
from .trace import Trace, read_trace, tool_counts, usage_summary


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


def result_path(out: Path, spec: RunSpec) -> Path:
    return out / "results" / f"{spec.run_id}.json"


def finished(out: Path, spec: RunSpec) -> bool:
    path = result_path(out, spec)
    return path.exists() and json.loads(path.read_text())["status"] != "error"


def run_one(spec: RunSpec, execute: Callable[[RunSpec, Trace], dict], out: Path) -> dict:
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
            result = {
                "status": "error",
                "error": {"kind": error.kind, "http_status": error.status, "message": str(error)[:4000]},
            }
        except Exception as error:
            result = {
                "status": "error",
                "error": {
                    "kind": type(error).__name__,
                    "message": str(error)[:4000],
                    "traceback": traceback.format_exc()[-8000:],
                },
            }
        if result["status"] == "error":
            trace.emit("error", **result["error"])
        trace.emit("run_end", status=result["status"])
    events = read_trace(trace_path)
    result = {
        "run_id": spec.run_id,
        **asdict(spec),
        **result,
        "usage": usage_summary(events),
        "tool_call_counts": tool_counts(events),
        "wall_seconds": round(time.monotonic() - start, 2),
        "source_digest": _source(),
    }
    write_json(result_path(out, spec), result)
    return result


def run_batch(
    specs: list[RunSpec],
    execute: Callable[[RunSpec, Trace], dict],
    out: Path,
    concurrency: int,
) -> dict[str, int]:
    """Run every unfinished spec; returns a count of result statuses."""
    pending = [spec for spec in specs if not finished(out, spec)]
    print(f"{len(specs) - len(pending)} finished, {len(pending)} to run", flush=True)
    statuses: dict[str, int] = {}
    with ThreadPoolExecutor(max(1, concurrency)) as pool:
        futures = {pool.submit(run_one, spec, execute, out): spec for spec in pending}
        for done, future in enumerate(as_completed(futures), start=1):
            result = future.result()
            statuses[result["status"]] = statuses.get(result["status"], 0) + 1
            print(f"[{done}/{len(pending)}] {result['run_id']}: {result['status']}", flush=True)
    return statuses
