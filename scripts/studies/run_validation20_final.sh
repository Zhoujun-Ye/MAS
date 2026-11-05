#!/usr/bin/env bash
# Fixed fixed overnight study. Never resumes or replaces an attempt.
set -uo pipefail
umask 077
cd "$(dirname "$0")/../.."
PY=/home/zhoujunye/MAS-information-data/environments/evaluation/bin/python
DATA=/home/zhoujunye/MAS-information-data
RUN=${1:?Supply a fresh absolute server output directory}
PROOFS=${2:?Supply matching offline proof directory}
if [[ "$RUN" != /home/zhoujunye/MAS-information/outputs/* || -e "$RUN" || -e "$RUN.driver-status.json" || -e "$RUN-report" ]]; then
  echo "Refusing existing or out-of-scope output" >&2
  exit 2
fi
"$PY" -m scripts.server.benchmark_matrix \
  --root "$DATA" --output "$RUN" --proofs "$PROOFS" \
  --image mas-information/research-benchmarks:20261103-v1 \
  --effort high --concurrency 6 --judge-concurrency 2 \
  --task-manifest docs/studies/validation20-v1-manifest.json \
  --protocol-settings docs/studies/validation20-final-protocol.json \
  --tasks-per-benchmark 20 --task-offset 0 \
  --authorized-attempts 120 --authorized-judges 106 --execute
matrix_status=$?
# Failed attempts remain in the summary and still get a report when available.
"$PY" -m scripts.studies.matched_matrix_report \
  --run "$RUN" --output "$RUN-export.json" --report-dir "$RUN-report"
report_status=$?
printf '{"matrix_exit_code":%d,"report_exit_code":%d,"finished_at":"%s"}\n' \
  "$matrix_status" "$report_status" "$(date -u +%FT%TZ)" > "$RUN.driver-status.json"
if (( matrix_status || report_status )); then
  exit 1
fi
