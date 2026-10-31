"""Benchmark-independent bounded dispatch and atomic JSON persistence."""
import json
from pathlib import Path
import threading
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait


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


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
