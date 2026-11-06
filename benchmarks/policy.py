"""Future-run solver timeouts; existing frozen runs retain their recorded settings."""

TIMEOUT_SECONDS_BY_BENCHMARK = {
    "dataclawbench": 1200,
    "hybriddeepresearch": 1800,
    "kramabench": 3600,
}

_SOURCES = {
    "dataclawbench": "Pinned upstream dataclaw/build_tasks.py:187; dataclaw/eval/run_batch.py:429,473,487",
    "hybriddeepresearch": "Engineering provisional default; no official solver timeout identified",
    "kramabench": "Engineering provisional default; no official solver timeout identified",
}


def default_timeout(benchmark):
    try:
        return TIMEOUT_SECONDS_BY_BENCHMARK[benchmark]
    except KeyError:
        raise ValueError("Unknown benchmark timeout policy: " + str(benchmark)) from None


def timeout_policy(benchmark, seconds=None):
    default = default_timeout(benchmark)
    effective = default if seconds is None else seconds
    if isinstance(effective, bool) or not isinstance(effective, int) or effective <= 0:
        raise ValueError("Solver timeout must be a positive integer number of seconds")
    return dict(default_seconds=default, effective_seconds=effective,
                default_basis="upstream_task_configuration" if benchmark == "dataclawbench" else "engineering_provisional",
                source_revision="32e138750ceba41b47290211403ad1781d5e1971" if benchmark == "dataclawbench" else None,
                source=_SOURCES[benchmark], overridden=effective != default)
