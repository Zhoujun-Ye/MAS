# Regression Tests

Run on the server with the existing project environment:

```sh
scripts/server/remote.sh '.venv/bin/python -m pytest -q'
```

Tests are grouped by behavior rather than historical revision numbers:

- `test_team*`: scheduling, dependencies, protocol, budgets and work boundaries.
- `test_comparison*` and `test_coordinator_baseline.py`: matched comparison contracts.
- `test_submission*`, `test_report_reservations_and_submission.py` and
  `test_final_capacity_preflight.py`: submission, transport and final-call capacity.
- `test_kramabench*`, `test_answer_metrics.py`, `test_semantic_judge.py`,
  `test_batch_pilot.py` and `test_pilot_audit.py`: benchmark adapters and tooling.
- Remaining modules cover shared execution, containers, inspection, accounting
  and historical analysis readers.

`conftest.py` blocks network connections; model interactions use scripted clients
or mock transports. Existing-image Docker checks are opt-in and may be skipped.
Passing this suite does not establish paid-run completion or answer correctness.
Keep historical run evidence outside this directory and retain regression tests
for repaired failures even when the original pilot has been retired.
