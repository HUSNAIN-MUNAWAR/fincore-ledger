#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Run Next.js first because its build workers are most reliable in a clean process state.
cd "$ROOT/apps/web"
rm -rf .next tsconfig.tsbuildinfo
NEXT_TELEMETRY_DISABLED=1 npm run build
npm run lint
npm run typecheck

cd "$ROOT/apps/api"
python -m ruff check .
python -m mypy fincore
python -m pytest -q
rm -f migration-check.db
FINCORE_DATABASE_URL=sqlite:///./migration-check.db alembic upgrade head
FINCORE_DATABASE_URL=sqlite:///./migration-check.db alembic downgrade base
rm -f migration-check.db

cd "$ROOT/packages/sdk"
npm run typecheck
