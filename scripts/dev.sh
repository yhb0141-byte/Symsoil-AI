#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
if [[ ! -x .venv/bin/python ]]; then python3 -m venv .venv; fi
.venv/bin/python -m pip install -r services/api/requirements.txt
export PYTHONPATH="$PROJECT_ROOT/services/api${PYTHONPATH:+:$PYTHONPATH}"
export SYMSOIL_WEB_DIST="$PROJECT_ROOT/apps/web/dist"
mkdir -p data
if [[ ! -d apps/web/node_modules ]]; then npm --prefix apps/web ci; fi
npm --prefix apps/web run build
exec .venv/bin/python -m uvicorn symsoil_api.main:app --host 127.0.0.1 --port "${PORT:-8000}"
