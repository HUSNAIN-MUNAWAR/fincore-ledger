# Security Model

## Protected assets

Financial journals, wallet authorization balances, credentials, refresh sessions, API keys, webhook secrets, tenant data, compliance decisions, and audit evidence are treated as protected assets.

## Trust boundaries

- Browsers and merchant clients are untrusted.
- JWT and API-key authentication establish identity, not authorization by themselves.
- Organization membership plus permissions establishes an operation context.
- Provider callbacks are untrusted until signature and replay checks pass.
- Background jobs are at-least-once and must be idempotent.

## Controls implemented

- Argon2 password hashes and failed-login lock protection.
- Short-lived JWT access tokens and hashed, revocable refresh sessions.
- Hashed merchant API keys with one-time secret display and scoped permissions.
- Route and service authorization, organization-scoped queries, and ownership checks.
- Pydantic validation, SQLAlchemy parameterization, safe domain-error envelopes, request IDs, correlation IDs, CORS, trusted-host middleware, request-size checks, security headers, and rate limiting.
- Money in integer minor units; transactional row locks; idempotency records; provider-event uniqueness; outbox persistence.
- HMAC webhook signatures; encrypted-at-rest signing secrets; one-time display and rotation-by-replacement model.
- Sensitive fields excluded from audit values and structured logs.

## Threat model summary

| Threat | Primary mitigation |
|---|---|
| Double spend | Wallet row lock, available-balance check, atomic journal/projection update |
| Duplicate client command | Idempotency key, request fingerprint, unique constraint, stored response |
| Cross-tenant access | Membership context, permissions, scoped queries, service ownership checks |
| Duplicate provider callback | Signature verification and unique provider event ID/reference |
| Webhook forgery/replay | HMAC timestamped payload and merchant-side replay guidance |
| Secret disclosure | Hash API/refresh tokens, encrypt webhook secrets, no raw card data |
| Partial financial commit | Single database transaction for operation, journal, audit, and outbox |
| Worker duplication | Persisted status/deduplication and idempotent state checks |

## Production requirements

Use a managed secret store and separate encryption keys, TLS everywhere, restrictive allowed hosts/origins, a gateway/WAF with distributed rate limits, private database/Redis networks, least-privilege database accounts, backups and restore drills, centralized tamper-resistant logs, SIEM alerts, SAST/DAST/dependency scanning, formal key rotation, penetration testing, incident response, and jurisdiction-specific compliance review.

See the root `SECURITY.md` for reporting and known limitations.
