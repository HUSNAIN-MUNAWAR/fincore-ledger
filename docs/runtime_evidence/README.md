# Runtime evidence

Run from the repository root:

```bash
python scripts/generate_runtime_evidence.py
```

The script creates a temporary SQLite database, applies the real SQLAlchemy
schema, seeds the committed UCI Online Retail sample through the real financial
services, runs the seed a second time to verify idempotency, and checks every
persisted journal for equal debit and credit totals. It writes:

- `ledger-runtime-trace.json` and `.csv` — measured journals and balances;
- `ledger-runtime-trace.mp4` and `ledger-runtime-trace-poster.jpg` — an
  animation rendered from those persisted journals;
- `summary.json` — dataset hash, seed counts, reconciliation result, video
  metadata, and artifact hashes.

The run uses SQLite development storage and the included development provider
boundary. It is evidence of the local ledger/reconciliation implementation, not
a claim of regulated payment processing, production PostgreSQL concurrency, or
real provider settlement.
