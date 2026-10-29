#!/usr/bin/env bash
# Copy scoped source to the server. Never credentials, environments, caches,
# data, outputs or --delete: files that exist only on the server are kept.
set -euo pipefail
cd "$(dirname "$0")/../.."
HOST="${SERVER:-zhoujunye@10.123.4.30}"
REMOTE="${REMOTE_DIR:-/home/zhoujunye/MAS-information}"
ssh -o BatchMode=yes "$HOST" "mkdir -p '$REMOTE'"
rsync -az -e "ssh -o BatchMode=yes" --exclude '__pycache__' --exclude '*.pyc' \
  AGENTS.md README.md pyproject.toml .gitignore configs mas_info scripts tests \
  "$HOST:$REMOTE/"
echo "synced to $HOST:$REMOTE"
