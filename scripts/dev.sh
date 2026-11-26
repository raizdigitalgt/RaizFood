#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
case "${1:-}" in
  backend) cd backend; exec .venv/bin/python -m uvicorn app.main:create_app --factory --reload --port 8000 ;;
  frontend) cd frontend; exec npm run dev ;;
  *) printf '%s\n' "Indica backend o frontend. Ejecuta un servicio en cada terminal." >&2; exit 2 ;;
esac
