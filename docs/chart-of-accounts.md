# Chart of Accounts

FinCore Ledger creates wallet accounts on demand and platform system accounts per currency. Codes are unique within an organization and currency.

| Code/pattern | Category | Normal balance | Purpose |
|---|---|---|---|
| `WALLET-<id>` | Liability | Credit | Customer or merchant funds owed by the platform |
| `DEPOSIT-CLEARING` | Asset | Debit | Confirmed provider funds receivable/clearing for deposits |
| `BANK-SETTLEMENT` | Asset | Debit | Cash/bank settlement movement for completed payouts |
| `FEE-REVENUE` | Revenue | Credit | Snapshotted transfer, payment, deposit, and withdrawal fees |
| Operator-defined suspense account | Suspense | Configured | Explicitly approved holding account for unresolved discrepancies |

## Ownership

Wallet accounts are owned by the wallet's organization. System clearing and revenue accounts are owned by the platform organization. A journal may post across these accounts while retaining the initiating operation's organization and correlation metadata.

## Currency

Every account and journal has exactly one three-letter currency. A journal cannot mix currencies. The application does not perform automatic FX conversion.

## Adding accounts

Production deployments should establish a reviewed account catalog, accounting policy, settlement mappings, legal-entity ownership, financial-statement grouping, and period-close controls. New administrative adjustments must use existing explicit account IDs; they cannot write directly to balances.
