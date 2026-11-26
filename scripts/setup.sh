#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
rf_python=${RAIZ_PYTHON:-python3.14}
"$rf_python" -c 'import sys; raise SystemExit(sys.version_info[:2] != (3, 14))'
test -x backend/.venv/bin/python || "$rf_python" -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements-dev.txt
if [[ ! -e .env ]]; then
  umask 077
  backend/.venv/bin/python -c 'import pathlib,secrets; pathlib.Path(".env").write_text(pathlib.Path(".env.example").read_text().replace("JWT_SECRET_KEY=", "JWT_SECRET_KEY=" + secrets.token_hex(32)), encoding="utf-8")'
fi
(cd backend && .venv/bin/python -m alembic upgrade head && .venv/bin/python -m app.cli seed-plans)
npm --prefix frontend ci
