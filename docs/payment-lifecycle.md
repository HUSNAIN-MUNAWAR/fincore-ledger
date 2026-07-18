# Payment Lifecycle

## States

`created`, `requires_action`, `processing`, `authorized`, `captured`, `partially_refunded`, `refunded`, `failed`, `cancelled`, and `expired` are modeled. The implemented wallet payment path uses validated transitions for automatic capture or manual authorization/capture.

```mermaid
stateDiagram-v2
    [*] --> Created
    Created --> Captured: automatic capture
    Created --> Authorized: manual capture
    Authorized --> Captured: capture command
    Captured --> PartiallyRefunded: partial refund
    Captured --> Refunded: full refund
    PartiallyRefunded --> PartiallyRefunded: additional partial refund
    PartiallyRefunded --> Refunded: remaining refund
    Created --> Failed
    Created --> Cancelled
    Created --> Expired
```

## Automatic capture

1. Validate tenant, wallet status, currency, limits, and available funds.
2. Snapshot the merchant-specific or default fee rule.
3. Lock customer and merchant wallets.
4. Persist payment and event history.
5. Post customer debit, merchant credit, and optional fee revenue.
6. Persist audit and outbox records.
7. Commit atomically and return a stable idempotent response.

## Manual capture

Authorization reduces customer available balance and increases reserved balance. Capture later posts the journal once, releases the reservation, changes the payment state, and emits the event.

## Refund flow

```mermaid
sequenceDiagram
    participant M as Merchant operator
    participant A as API
    participant S as Payment service
    participant L as Ledger
    M->>A: POST /payments/{id}/refunds + idempotency key
    A->>S: Validate permission and merchant ownership
    S->>S: Lock payment and calculate refundable amount
    S->>L: Debit merchant liability / credit customer liability
    S->>S: Persist refund, payment state, audit, outbox
    A-->>M: Completed refund record
```

Fees are not automatically returned in the current business-refund policy. A different fee policy should be implemented explicitly rather than mutating historical fee snapshots.
