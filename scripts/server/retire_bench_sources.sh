#!/usr/bin/env bash
# One-time, reversible retirement of the adapters removed on 2026-10-29.
# Deliberately not rsync --delete; never touch upstream/assets/outputs/envs.
set -euo pipefail
cd "$(dirname "$0")/../.."
if [[ "${1:-}" != --apply ]]; then
  echo "Pass --apply to archive only the explicit retired source-file list."
  exit 0
fi
archive=.retired_sources/leader-led-team-20261029
while IFS= read -r path; do
  [[ -n "$path" ]] || continue
  if [[ -f "$path" ]]; then
    if [[ -e "$archive/$path" ]]; then
      echo "Archive already contains $path; refusing to overwrite" >&2
      exit 1
    fi
    mkdir -p "$archive/$(dirname "$path")"
    mv "$path" "$archive/$path"
    printf 'retired %s\n' "$path"
  fi
done <<'FILES'
benchmarks/bfcl/__init__.py
benchmarks/bfcl/adapter.py
benchmarks/toolhop/__init__.py
benchmarks/toolhop/adapter.py
scripts/bfcl/prepare.py
scripts/bfcl/run.py
scripts/bfcl/summarize.py
scripts/toolhop/prepare.py
scripts/toolhop/run.py
configs/experiment1.yaml
configs/toolhop.yaml
tests/test_bfcl_native.py
tests/test_toolhop.py
benchmarks/browsecomp_plus/__init__.py
benchmarks/browsecomp_plus/arrival.py
benchmarks/browsecomp_plus/data.py
benchmarks/browsecomp_plus/diagnostics.py
benchmarks/browsecomp_plus/grade.py
benchmarks/browsecomp_plus/prompts.py
benchmarks/browsecomp_plus/retriever.py
benchmarks/browsecomp_plus/system.py
benchmarks/browsecomp_plus/tools.py
benchmarks/tau2_bench/__init__.py
benchmarks/tau2_bench/diagnostics.py
benchmarks/tau2_bench/prompts.py
benchmarks/tau2_bench/run.py
benchmarks/tau2_bench/team.py
configs/browsecomp_plus.yaml
configs/tau2_bench.yaml
scripts/browsecomp_plus/grade.py
scripts/browsecomp_plus/judge_arrival.py
scripts/browsecomp_plus/prepare.py
scripts/browsecomp_plus/run.py
scripts/tau2_bench/run.py
tests/test_arrival.py
tests/test_browsecomp_plus.py
tests/test_tau2_bench.py
FILES
