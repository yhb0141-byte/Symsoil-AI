#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
export PYTHONPATH="$PROJECT_ROOT/services/api${PYTHONPATH:+:$PYTHONPATH}"
.venv/bin/python -m pytest services/api/tests -q
npm --prefix apps/web run typecheck
npm --prefix apps/web test
npm --prefix apps/web run build
