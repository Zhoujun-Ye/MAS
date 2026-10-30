#!/usr/bin/env bash
# Reversibly retire only TravelPlanner source; preserve all data and past runs.
set -euo pipefail
cd "$(dirname "$0")/../.."
if [[ "${1:-}" != --apply ]]; then
  echo "Pass --apply to archive TravelPlanner source only."
  exit 0
fi
archive=.retired_sources/travelplanner-20261029
paths=(
  benchmarks/travelplanner/__init__.py
  benchmarks/travelplanner/adapter.py
  benchmarks/travelplanner/native_worker.py
  scripts/travelplanner/prepare.py
  scripts/travelplanner/offline.py
  scripts/travelplanner/run.py
  tests/test_travelplanner.py
)
for path in "${paths[@]}"; do
  if [[ -f "$path" && -e "$archive/$path" ]]; then
    echo "Archive already contains $path; refusing to overwrite" >&2
    exit 1
  fi
done
for path in "${paths[@]}"; do
  if [[ -f "$path" ]]; then
    mkdir -p "$archive/$(dirname "$path")"
    mv "$path" "$archive/$path"
    printf 'retired %s\n' "$path"
  fi
done
