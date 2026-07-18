#!/bin/sh
set -eu
alembic upgrade head
if [ "${FINCORE_SEED_ON_START:-false}" = "true" ]; then
  python -m fincore.seed
fi
exec uvicorn fincore.main:app --host 0.0.0.0 --port 8000
