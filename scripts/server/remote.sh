#!/usr/bin/env bash
# Run a command in the server project directory, e.g.
#   scripts/server/remote.sh '.venv/bin/python -m pytest -q'
# Uses key login. Without a key, load .env and use ssh.exp instead.
set -euo pipefail
HOST="${SERVER:-zhoujunye@10.123.4.30}"
REMOTE="${REMOTE_DIR:-/home/zhoujunye/MAS-information}"
exec ssh -o BatchMode=yes "$HOST" "cd '$REMOTE' && $*"
