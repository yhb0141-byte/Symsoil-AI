#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
if [[ ! -x .venv/bin/python ]]; then
  printf '%s\n' '请先按 README 安装后端依赖。' >&2
  exit 1
fi
if [[ -z "${SYMSOIL_DEMO_PASSWORD:-}" ]]; then
  read -r -s -p '设置本机合成演示口令（至少12字符）: ' SYMSOIL_DEMO_PASSWORD
  printf '\n'
fi
export SYMSOIL_DEMO_PASSWORD
export PYTHONPATH="$PROJECT_ROOT/services/api${PYTHONPATH:+:$PYTHONPATH}"
mkdir -p data
exec .venv/bin/python -m symsoil_api.cli seed --demo
