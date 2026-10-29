#!/usr/bin/env bash
# Run on the server from the project root: pinned upstream checkouts, the
# virtual environment and the protected provider key. Safe to rerun.
set -euo pipefail
cd "$(dirname "$0")/../.."
UV="${UV:-/home/zhoujunye/agent-team/.runtime/uv/bin/uv}"
# Downloads from pypi.org stall on this server; the Tsinghua mirror serves the same files.
export UV_DEFAULT_INDEX="${UV_DEFAULT_INDEX:-https://pypi.tuna.tsinghua.edu.cn/simple}"

checkout() {  # url directory commit
  if [[ ! -d "$2/.git" ]]; then
    git clone --quiet "$1" "$2"
  fi
  git -C "$2" fetch --quiet origin "$3" || true
  git -C "$2" checkout --quiet "$3"
  echo "$2 @ $(git -C "$2" rev-parse HEAD)"
}
checkout https://github.com/texttron/BrowseComp-Plus external/BrowseComp-Plus 046949032b0328319cc9a02663a759ec601d9402
checkout https://github.com/sierra-research/tau2-bench external/tau2-bench 122e2432b82d740e8f313f46f0a071729c404f39

if [[ ! -x .venv/bin/python ]]; then
  "$UV" venv --python 3.12 .venv
fi
"$UV" pip install --python .venv/bin/python -e ".[test]" -e external/tau2-bench pyjnius==1.9.0
# The official BM25 path needs only pyserini's Lucene bindings, not its neural stack.
"$UV" pip install --python .venv/bin/python --no-deps pyserini==1.2.0

# The provider key stays on this host: reuse the server's own protected .env.
if [[ ! -e .env ]]; then
  install -m 600 /home/zhoujunye/agent-team/.env .env
fi
stat -c '%a %n' .env
