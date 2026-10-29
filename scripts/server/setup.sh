#!/usr/bin/env bash
# Core dependencies only. No benchmark downloads, installs or model calls.
set -euo pipefail
cd "$(dirname "$0")/../.."
UV="${UV:-/home/zhoujunye/.local/bin/uv}"
export UV_DEFAULT_INDEX="${UV_DEFAULT_INDEX:-https://pypi.tuna.tsinghua.edu.cn/simple}"
if [[ ! -x .venv/bin/python ]]; then
  "$UV" venv --python 3.12 .venv
fi
"$UV" pip install --python .venv/bin/python -e ".[test]"
# Existing environments/caches and historical benchmark assets are not removed.
if [[ ! -e .env ]]; then
  install -m 600 /home/zhoujunye/agent-team/.env .env
fi
stat -c '%a %n' .env
