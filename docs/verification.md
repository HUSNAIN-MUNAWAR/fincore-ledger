# Verification Record

Verification was refreshed on July 19, 2026 (Asia/Karachi) in the project workspace after integrating the UCI Online Retail public dataset demo.

## Dataset Workflow

Commands:

```bash
python scripts/prepare_uci_online_retail_sample.py --skip-download
cd apps/api
python -m pytest tests/test_public_dataset_seed.py -q
```

Results:

- Processed sample generated at `data/sample/uci_online_retail_payments.json`.
- Sample contains 18 invoice-derived GBP payments and 1 cancellation-derived refund.
- Dataset seed test passed: 2 passed, with one upstream `StarletteDeprecationWarning`.
- Fresh migrated SQLite seed result: 18 payments created, 1 refund created, 1 withdrawal created, 2 wallet projections matched, 0 reconciliation mismatches.

## Backend

Commands:

```bash
cd apps/api
python -m ruff check .
python -m mypy fincore/public_dataset_seed.py --follow-imports=skip --ignore-missing-imports --no-incremental
python -m pytest -q
python -m compileall -q fincore
```

Results:

- Ruff: all checks passed.
- MyPy: no issues found in `fincore/public_dataset_seed.py` with import following skipped; the full `python -m mypy fincore --no-incremental` command timed out locally after 10 minutes without producing diagnostics.
- Pytest: 18 passed, with one upstream `StarletteDeprecationWarning` from the globally installed FastAPI/TestClient stack.
- Compile check: completed successfully.

Notes:

- Test fixtures use in-memory SQLite with `StaticPool` to avoid local file-lock collisions and stale SQLite journal files.
- The local Python environment had newer global packages than the pinned requirements. The source was adjusted for current `ruff`, `mypy`, and `pydantic-settings` compatibility.

## Frontend

The checked-out `apps/web/node_modules` directory was a stale partial install and locked by Windows. To verify from a clean dependency tree, the web source was copied to a temporary directory without `node_modules`, using the repository lockfile after replacing internal registry URLs with `https://registry.npmjs.org/`.

Commands:

```bash
cd <temporary clean web copy>
npm ci --registry=https://registry.npmjs.org/
npm run lint
npm run typecheck
NEXT_TELEMETRY_DISABLED=1 npm run build
npm audit --audit-level=moderate
```

Results:

- npm install: 364 packages installed, 0 vulnerabilities.
- ESLint: passed with zero warnings.
- TypeScript: passed.
- Next.js production build: passed; 12 static routes generated.
- npm audit: 0 vulnerabilities.

## SDK

The SDK package was verified from its existing lockfile.

```bash
cd packages/sdk
npm ci --registry=https://registry.npmjs.org/
npm run typecheck
npm run build
npm audit --audit-level=moderate
```

Results:

- npm install: 3 packages installed, 0 vulnerabilities.
- TypeScript type check: passed.
- SDK build: passed.
- npm audit: 0 vulnerabilities.

## Live Smoke

A SQLite demo database was migrated and seeded, then the FastAPI server and production Next.js server were started locally.

Commands:

```bash
cd apps/api
FINCORE_DATABASE_URL=sqlite:///.../fincore-demo.db alembic upgrade head
FINCORE_DATABASE_URL=sqlite:///.../fincore-demo.db python -m fincore.seed
uvicorn fincore.main:app --host 127.0.0.1 --port 8012

cd apps/web
npm run start -- -p 3001

FINCORE_API_URL=http://127.0.0.1:8012/api/v1 python scripts/smoke_test.py
```

Results:

- `GET /health/live` returned `{"status":"live"}`.
- Smoke test passed against the public dataset seed with one customer wallet and an available balance of `50465` GBP minor units after the smoke transaction.
- Screenshots in `docs/screenshots/` were captured from the locally running app with UCI Online Retail payment, refund, payout, webhook, ledger, and reconciliation data.

## Docker

Docker was not installed in this workspace (`docker` was not recognized), so Docker image builds and Docker Compose startup could not be executed locally. The Compose file and Dockerfiles remain included, and GitHub Actions runs source-level backend, frontend, and SDK checks.
