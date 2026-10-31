#!/usr/bin/env bash
# New official combinations; selection and all offline gates precede payment.
set -euo pipefail
cd "$(dirname "$0")/../.."
[[ $# == 1 && "$1" == --authorized-new-100-paid-pairs-once ]] || exit 2
RUN="${NEW100_RUN:-new100-20261031-01}"
SETUP="outputs/setup/$RUN"
PY=.venv/bin/python
mkdir "$SETUP"
$PY scripts/cooperbench/select_pairs.py --new-100 --output "$SETUP/selection.json" > "$SETUP/selection.log"
$PY -m pytest -q > "$SETUP/regression.log" 2>&1
$PY scripts/cooperbench/check_exchange.py --selection "$SETUP/selection.json" --output "$SETUP/exchange" --authorized-local-evaluation > "$SETUP/exchange.log" 2>&1
$PY scripts/cooperbench/verify_workers.py --all-tasks --output "$SETUP/workers" --authorized-local-evaluation > "$SETUP/workers.log" 2>&1
$PY scripts/cooperbench/native_check.py --all-tasks --selection "$SETUP/selection.json" --jobs 4 --output "$SETUP/gates" --authorized-local-evaluation > "$SETUP/gates.log" 2>&1
$PY scripts/cooperbench/pilot.py --selection "$SETUP/selection.json" --gates "$SETUP/gates/selected" --environment-gates "$SETUP/gates/all" --output "outputs/cooperbench/$RUN" --task-concurrency 4 --authorized-new-100-paid-pairs-once > "$SETUP/paid.log" 2>&1
