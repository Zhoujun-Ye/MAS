#!/usr/bin/env bash
# Copy scoped source to the server. Never credentials, environments, caches,
# benchmark checkouts or assets, outputs or --delete: server-only files are kept.
set -euo pipefail
cd "$(dirname "$0")/../.."
HOST="${SERVER:-zhoujunye@10.123.4.30}"
REMOTE="${REMOTE_DIR:-/home/zhoujunye/mas}"
ssh -o BatchMode=yes "$HOST" "mkdir -p '$REMOTE'"
if (( $# )); then
  # Explicit source-only mode for a narrow change; never sync runtime data.
  for path in "$@"; do
    case "$path" in
      *..*|/*|*assets/*|*upstream/*|*__pycache__*|*.pyc) echo "Refusing $path" >&2; exit 1 ;;
      common/*.py|harness/*.py|harness/README.md|harness/*/README.md|benchmarks/*.py|analysis/*.py|scripts/*.py|scripts/*.sh|scripts/README.md|scripts/common/prompts/README.md|scripts/studies/causal_experiments/README.md|tests/*.py|docs/*.md|docs/studies/*.txt|docs/studies/validation20-v1-manifest.json|docs/studies/validation20-final-protocol.json|docs/studies/cpu8-infra-protocol.json|AGENTS.md|README.md|pyproject.toml) ;;
      *) echo "Not a scoped source path: $path" >&2; exit 1 ;;
    esac
    [[ -f "$path" && ! -L "$path" ]] || { echo "Not a regular source file: $path" >&2; exit 1; }
  done
  rsync -azR -e "ssh -o BatchMode=yes" "$@" "$HOST:$REMOTE/"
  echo "synced scoped files to $HOST:$REMOTE"
  exit 0
fi
rsync -az -e "ssh -o BatchMode=yes" \
  --exclude '__pycache__' --exclude '*.pyc' --exclude 'upstream/' --exclude 'assets/' \
  AGENTS.md README.md pyproject.toml .gitignore .env.example \
  common harness benchmarks analysis scripts tests docs \
  "$HOST:$REMOTE/"
echo "synced to $HOST:$REMOTE"
