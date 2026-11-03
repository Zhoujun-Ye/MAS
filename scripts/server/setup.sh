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
# Provider credentials are supplied separately. Never copy another project's .env.
# External CLIs and their Python runtimes are not installed by this script.
