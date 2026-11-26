#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
(cd backend && .venv/bin/python -m ruff check && .venv/bin/python -m pytest --cov=app --cov-fail-under=80)
cd frontend
npm run lint
npm run typecheck
npm run build
if [[ "${1:-}" == "--browser" ]]; then npm run test:e2e; fi
