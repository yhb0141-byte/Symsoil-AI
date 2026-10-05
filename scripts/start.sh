#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
if [[ ! -x .venv/bin/python || ! -f apps/web/dist/index.html ]]; then
  echo '请先按 README 安装依赖并构建网页；start.sh 不下载依赖。' >&2
  exit 1
fi
export PYTHONPATH="$PROJECT_ROOT/services/api${PYTHONPATH:+:$PYTHONPATH}"
export SYMSOIL_WEB_DIST="$PROJECT_ROOT/apps/web/dist"
mkdir -p data
exec .venv/bin/python -m uvicorn symsoil_api.main:app --host 127.0.0.1 --port "${PORT:-8000}"
