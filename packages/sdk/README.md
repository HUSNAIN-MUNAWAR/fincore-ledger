# @fincore/sdk

TypeScript client for the real FinCore API endpoints. It supports API-key authentication, idempotent payment creation, retrieval, refunds, wallet listing, and constant-time webhook signature verification.

```ts
const client = new FinCoreClient({ apiKey: process.env.FINCORE_API_KEY! });
const payment = await client.payments.create({
  customer_wallet_id: "...",
  merchant_wallet_id: "...",
  amount: 250000,
  currency: "PKR",
  reference: "ORDER-1007"
}, "order-1007-payment");
```
