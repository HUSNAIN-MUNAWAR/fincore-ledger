# API Examples

Base URL: `http://localhost:8000/api/v1`. All amounts are integer minor units.

## Login

```bash
LOGIN=$(curl -s http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"customer@fincore.example","password":"FinCore-Dev-2026!"}')
ACCESS_TOKEN=$(python -c 'import json,sys; print(json.load(sys.stdin)["access_token"])' <<< "$LOGIN")
```

## List wallets

```bash
curl -s http://localhost:8000/api/v1/wallets \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

## Create transfer

```bash
curl -s -X POST http://localhost:8000/api/v1/transfers \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: transfer-2026-0001' \
  -d '{
    "sender_wallet_id":"<sender-wallet-id>",
    "receiver_wallet_id":"<receiver-wallet-id>",
    "amount":50000,
    "currency":"PKR",
    "reference":"TRANSFER-0001",
    "description":"Internal settlement"
  }'
```

Replaying the same request and key returns the stored response. Reusing the key with changed input returns `409 IDEMPOTENCY_CONFLICT`.

## Create wallet payment

```bash
curl -s -X POST http://localhost:8000/api/v1/payments \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: order-1007-payment' \
  -d '{
    "customer_wallet_id":"<customer-wallet-id>",
    "merchant_wallet_id":"<merchant-wallet-id>",
    "amount":250000,
    "currency":"PKR",
    "reference":"ORDER-1007",
    "description":"Equipment inspection subscription",
    "capture_method":"automatic",
    "metadata":{"order_id":"1007"}
  }'
```

## Refund

Use a merchant access token or API key with refund permission.

```bash
curl -s -X POST http://localhost:8000/api/v1/payments/<payment-id>/refunds \
  -H "Authorization: Bearer $MERCHANT_ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: refund-order-1007-1' \
  -d '{"amount":50000,"reason":"Partial service credit"}'
```

## Request and approve withdrawal

```bash
curl -s -X POST http://localhost:8000/api/v1/withdrawals \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: payout-0001' \
  -d '{
    "wallet_id":"<wallet-id>",
    "amount":100000,
    "currency":"PKR",
    "destination_masked":"PK** **** 4455",
    "reference":"PAYOUT-0001"
  }'
```

```bash
curl -s -X POST http://localhost:8000/api/v1/withdrawals/<withdrawal-id>/approve \
  -H "Authorization: Bearer $OPS_ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"note":"Development review completed"}'
```

A provider request leaves the withdrawal in `processing`. Development completion is a separate explicitly authorized operation.

## Create API key

```bash
curl -s -X POST http://localhost:8000/api/v1/api-keys \
  -H "Authorization: Bearer $MERCHANT_ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name":"Checkout service","scopes":["payments:read","payments:write","refunds:write"]}'
```

The secret is returned once; only its hash and prefix remain stored.

## Webhook signature verification

Webhook requests include a signature of the canonical payload using HMAC-SHA256. The TypeScript SDK exports `verifyWebhookSignature`. Consumers should also reject old timestamps and persist event IDs to prevent replay.

## Error envelope

```json
{
  "error": {
    "code": "INSUFFICIENT_FUNDS",
    "message": "The wallet does not have sufficient available funds.",
    "request_id": "req_..."
  }
}
```
