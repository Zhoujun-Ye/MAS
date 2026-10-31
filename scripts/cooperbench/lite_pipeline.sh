#!/usr/bin/env bash
# Explicitly authorized one-pass lite batch. Every offline gate precedes payment.
set -euo pipefail
cd "$(dirname "$0")/../.."
[[ $# == 1 && "$1" == --authorized-lite-100-paid-pairs-once ]] || exit 2
RUN="${LITE_RUN:-lite100-20261030-02}"
SETUP="outputs/setup/$RUN"
PY=.venv/bin/python
mkdir "$SETUP"
$PY scripts/cooperbench/select_pairs.py --lite --output "$SETUP/selection.json" > "$SETUP/selection.log"
$PY -m pytest -q > "$SETUP/regression.log" 2>&1
$PY scripts/cooperbench/check_exchange.py --selection "$SETUP/selection.json" --output "$SETUP/exchange" --authorized-local-evaluation > "$SETUP/exchange.log" 2>&1
$PY scripts/cooperbench/verify_workers.py --all-tasks --output "$SETUP/workers" --authorized-local-evaluation > "$SETUP/workers.log" 2>&1
$PY scripts/cooperbench/native_check.py --all-tasks --jobs 4 --output "$SETUP/environment-gates" --authorized-local-evaluation > "$SETUP/environment-gates.log" 2>&1
$PY scripts/cooperbench/native_check.py --selection "$SETUP/selection.json" --jobs 4 --output "$SETUP/selected-gates" --authorized-local-evaluation > "$SETUP/selected-gates.log" 2>&1
$PY scripts/cooperbench/pilot.py --selection "$SETUP/selection.json" --gates "$SETUP/selected-gates" --environment-gates "$SETUP/environment-gates" --output "outputs/cooperbench/$RUN" --task-concurrency 4 --authorized-lite-100-paid-pairs-once > "$SETUP/paid.log" 2>&1
