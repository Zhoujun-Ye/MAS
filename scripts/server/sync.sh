#!/usr/bin/env bash
# Copy scoped source to the server. Never credentials, environments, caches,
# benchmark checkouts or assets, outputs or --delete: server-only files are kept.
set -euo pipefail
cd "$(dirname "$0")/../.."
HOST="${SERVER:-zhoujunye@10.123.4.30}"
REMOTE="${REMOTE_DIR:-/home/zhoujunye/MAS-information}"
ssh -o BatchMode=yes "$HOST" "mkdir -p '$REMOTE'"
rsync -az -e "ssh -o BatchMode=yes" \
  --exclude '__pycache__' --exclude '*.pyc' --exclude 'upstream/' --exclude 'assets/' \
  AGENTS.md README.md pyproject.toml .gitignore .env.example \
  configs harness benchmarks analysis scripts tests docs \
  "$HOST:$REMOTE/"
echo "synced to $HOST:$REMOTE"
