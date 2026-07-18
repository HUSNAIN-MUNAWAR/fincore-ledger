# Production Readiness

FinCore Ledger is an engineering reference, not a claim of regulatory or operational authorization.

## Implemented baseline

- Ledger-first double-entry accounting and immutable posting history.
- Transactional wallet projections, row-lock intent, limits, fees, state machines, idempotency, audit, and outbox.
- JWT/refresh sessions, roles/permissions, tenant checks, API-key hashing, webhook signatures, and safe errors.
- Reconciliation records, compliance review workflow, administrative adjustments, reports, health checks, CI, and tests.

## Must be completed before real money

### Legal and compliance

Determine licensing and safeguarding obligations, AML/KYC/KYB program, sanctions/PEP screening, suspicious-activity reporting, data residency, privacy rights, consumer protection, complaints, tax, record retention, and payment-network contracts for every jurisdiction.

### Financial controls

Establish approved chart of accounts, legal-entity books, daily provider/bank reconciliation, four-eyes adjustments, settlement cutoffs, period close, suspense aging, treasury limits, fee/tax policy, independent finance review, and immutable evidence retention.

### Security

Perform architecture threat modeling, SAST/DAST/SCA, penetration tests, secret/key rotation, HSM/KMS adoption, privileged-access management, production network isolation, hardened images, WAF/DDoS controls, endpoint monitoring, SIEM response, breach playbooks, and backup recovery exercises.

### Reliability

Load and concurrency test on PostgreSQL, exercise failover, bound retries, monitor stuck states/outbox lag, define RPO/RTO, test provider outages and duplicate callbacks, add chaos tests, and operate a 24/7 incident and reconciliation process where required.

### Product gaps

- Integrate and certify an official sandbox/provider adapter.
- Implement jurisdiction-approved identity/document providers and transaction-monitoring rules.
- Add email verification/password reset delivery, MFA/passkeys, and stronger session/device controls.
- Add complete provider settlement imports, disputes/chargebacks, merchant settlement schedules, tax invoices, and accounting exports as required.
- Expand browser E2E coverage and accessibility/security testing.

## Go-live gate

A go-live decision should require written approval from engineering, security, finance, operations, compliance/legal, and the regulated/payment partners. Passing this repository's automated tests is necessary but not sufficient.
