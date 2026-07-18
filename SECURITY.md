# Security Policy

FinCore Ledger is an engineering reference platform, not a licensed payment institution and not certified for PCI DSS, SOC 2, or any jurisdictional financial regime.

## Reporting a Vulnerability

Report suspected vulnerabilities privately to the repository owner through GitHub. Do not open public issues containing exploit details, tokens, signing secrets, local database dumps, or real financial/customer data.

Please include:

- A concise description of the issue.
- Reproduction steps or proof-of-concept requests using demo data only.
- Affected component: API, web app, SDK, worker, Docker, or docs.
- Any suggested mitigation.

## Security Model

The implementation addresses cross-tenant access, credential theft, replayed requests, duplicate provider callbacks, double spending, inconsistent ledger posting, webhook forgery, and sensitive-data leakage. Controls include scoped permissions, Argon2 password hashing, short-lived JWTs, hashed refresh sessions and API keys, HMAC webhook signatures, request idempotency, unique constraints, transactional journal posting, and row locks on debit wallets.

## Secret Handling

Production secrets must be supplied through a secret manager. Never commit `.env`, provider credentials, signing secrets, raw access tokens, full card data, CVV, online-banking credentials, local databases, or production logs. Webhook and API-key secrets are shown only at creation or rotation.

## Known Hardening Work

The local provider is development-only. Production deployments need independent penetration testing, TLS termination, managed key rotation, jurisdiction-specific KYC/AML and licensing review, database encryption, backup/restore drills, WAF/rate-limit enforcement, SIEM integration, data-retention policy, and an official payment-provider sandbox/certification program.
