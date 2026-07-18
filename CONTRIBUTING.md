# Contributing

Thanks for taking the time to improve FinCore Ledger.

## Development Principles

- Preserve double-entry accounting invariants. Never mutate posted journal entries or directly overwrite wallet balances to "fix" history.
- Keep tenant isolation explicit in API queries, service calls, tests, and UI assumptions.
- Money-moving endpoints must support idempotency and reject negative available or ledger balances.
- Treat provider integrations, webhooks, credentials, and audit logs as security-sensitive code.
- Keep demo data fictional and clearly labeled.

## Local Checks

Run the checks that match your change:

```bash
cd apps/api
python -m ruff check .
python -m mypy fincore --no-incremental
python -m pytest -q
```

```bash
cd apps/web
npm ci
npm run lint
npm run typecheck
npm run build
```

```bash
cd packages/sdk
npm ci
npm run typecheck
npm run build
```

## Pull Requests

Use a focused branch, include tests for financial behavior, and document any migration, security, or compatibility impact. Security-sensitive changes should include threat-model notes and should not disclose secrets or real customer financial data.
