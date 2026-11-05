#!/usr/bin/env bash
# Run a command in the server project directory, e.g.
#   scripts/server/remote.sh '.venv/bin/python -m pytest -q'
# Requires configured key-based SSH authentication; no credential fallback.
set -euo pipefail
HOST="${SERVER:-zhoujunye@10.123.4.30}"
REMOTE="${REMOTE_DIR:-/home/zhoujunye/MAS-information}"
exec ssh -o BatchMode=yes "$HOST" "cd '$REMOTE' && $*"
