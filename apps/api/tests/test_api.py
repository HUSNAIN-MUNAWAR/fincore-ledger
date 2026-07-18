from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def login(client: TestClient, email: str) -> dict[str, object]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": "StrongPassword!123"})
    assert response.status_code == 200, response.text
    return response.json()


def test_login_tenant_isolation_and_idempotency(
    client: TestClient, db: Session, seeded: dict[str, object]
) -> None:
    from fincore.services.financial import complete_deposit, create_deposit

    customer_org = seeded["customer_org"]
    customer = seeded["customer"]
    wallet = seeded["customer_wallet"]
    other_wallet = seeded["other_wallet"]
    deposit = create_deposit(
        db, organization_id=customer_org.id, actor_id=customer.id, wallet_id=wallet.id,  # type: ignore[attr-defined]
        amount=100_000, currency="PKR", reference="API-FUND"
    )
    complete_deposit(db, deposit_id=deposit.id, actor_id=customer.id, authorized_development_confirmation=True)  # type: ignore[attr-defined]
    db.commit()
    token = login(client, "customer@test.example")
    headers = {"Authorization": f"Bearer {token['access_token']}"}
    wallets = client.get("/api/v1/wallets", headers=headers)
    assert wallets.status_code == 200
    assert len(wallets.json()) == 1
    assert wallets.json()[0]["id"] == wallet.id  # type: ignore[attr-defined]
    forbidden = client.get(f"/api/v1/wallets/{other_wallet.id}", headers=headers)  # type: ignore[attr-defined]
    assert forbidden.status_code == 404

    body = {
        "sender_wallet_id": wallet.id,  # type: ignore[attr-defined]
        "receiver_wallet_id": other_wallet.id,  # type: ignore[attr-defined]
        "amount": 10_000,
        "currency": "PKR",
        "reference": "IDEM-1",
        "description": "same request",
    }
    idem_headers = headers | {"Idempotency-Key": "test-idempotency-0001"}
    first = client.post("/api/v1/transfers", json=body, headers=idem_headers)
    second = client.post("/api/v1/transfers", json=body, headers=idem_headers)
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["id"] == second.json()["id"]
    conflict = client.post(
        "/api/v1/transfers", json=body | {"amount": 11_000}, headers=idem_headers
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_api_end_to_end_customer_payment_and_operations_payout(
    client: TestClient, db: Session, seeded: dict[str, object]
) -> None:
    from fincore.services.financial import complete_deposit, create_deposit

    customer_org = seeded["customer_org"]
    merchant_org = seeded["merchant_org"]
    customer = seeded["customer"]
    merchant = seeded["merchant"]
    customer_wallet = seeded["customer_wallet"]
    merchant_wallet = seeded["merchant_wallet"]
    for org, user, wallet, amount, reference in [
        (customer_org, customer, customer_wallet, 500_000, "E2E-CUSTOMER"),
        (merchant_org, merchant, merchant_wallet, 200_000, "E2E-MERCHANT"),
    ]:
        deposit = create_deposit(
            db,
            organization_id=org.id,  # type: ignore[attr-defined]
            actor_id=user.id,  # type: ignore[attr-defined]
            wallet_id=wallet.id,  # type: ignore[attr-defined]
            amount=amount,
            currency="PKR",
            reference=reference,
        )
        complete_deposit(
            db,
            deposit_id=deposit.id,
            actor_id=user.id,  # type: ignore[attr-defined]
            authorized_development_confirmation=True,
        )
    db.commit()

    customer_token = login(client, "customer@test.example")
    customer_headers = {"Authorization": f"Bearer {customer_token['access_token']}"}
    payment_response = client.post(
        "/api/v1/payments",
        headers=customer_headers | {"Idempotency-Key": "e2e-payment-key-0001"},
        json={
            "customer_wallet_id": customer_wallet.id,  # type: ignore[attr-defined]
            "merchant_wallet_id": merchant_wallet.id,  # type: ignore[attr-defined]
            "amount": 75_000,
            "currency": "PKR",
            "reference": "E2E-ORDER-1",
            "description": "End-to-end order",
            "metadata": {"source": "api-e2e"},
            "capture_method": "automatic",
        },
    )
    assert payment_response.status_code == 201, payment_response.text
    assert payment_response.json()["status"] == "captured"

    merchant_token = login(client, "merchant@test.example")
    merchant_headers = {"Authorization": f"Bearer {merchant_token['access_token']}"}
    merchant_payments = client.get("/api/v1/payments", headers=merchant_headers)
    assert merchant_payments.status_code == 200
    assert any(item["reference"] == "E2E-ORDER-1" for item in merchant_payments.json())
    withdrawal_response = client.post(
        "/api/v1/withdrawals",
        headers=merchant_headers | {"Idempotency-Key": "e2e-withdrawal-key-0001"},
        json={
            "wallet_id": merchant_wallet.id,  # type: ignore[attr-defined]
            "amount": 50_000,
            "currency": "PKR",
            "destination_masked": "Bank •••• 9001",
            "reference": "E2E-PAYOUT-1",
        },
    )
    assert withdrawal_response.status_code == 201, withdrawal_response.text
    withdrawal_id = withdrawal_response.json()["id"]

    admin_token = login(client, "admin@test.example")
    admin_headers = {"Authorization": f"Bearer {admin_token['access_token']}"}
    approval = client.post(
        f"/api/v1/withdrawals/{withdrawal_id}/approve",
        headers=admin_headers,
        json={"note": "E2E operations approval"},
    )
    assert approval.status_code == 200, approval.text
    completion = client.post(
        f"/api/v1/development/withdrawals/{withdrawal_id}/confirm",
        headers=admin_headers,
    )
    assert completion.status_code == 200, completion.text
    assert completion.json()["status"] == "completed"

    journals = client.get("/api/v1/ledger/journals", headers=admin_headers)
    assert journals.status_code == 200
    references = {item["reference"] for item in journals.json()}
    assert {"E2E-ORDER-1", "E2E-PAYOUT-1"}.issubset(references)
    assert all(item["balanced"] for item in journals.json())
    reconciliation = client.post("/api/v1/reconciliation/runs", headers=admin_headers)
    assert reconciliation.status_code == 201
    assert reconciliation.json()["mismatch_count"] == 0


def test_api_key_rotation_and_scoped_authentication(
    client: TestClient, db: Session, seeded: dict[str, object]
) -> None:
    merchant_token = login(client, "merchant@test.example")
    bearer = {"Authorization": f"Bearer {merchant_token['access_token']}"}
    created = client.post(
        "/api/v1/api-keys",
        headers=bearer,
        json={"name": "Read payments", "scopes": ["payments.read"]},
    )
    assert created.status_code == 201, created.text
    first_id = created.json()["key"]["id"]
    first_secret = created.json()["secret"]

    payment_list = client.get("/api/v1/payments", headers={"X-API-Key": first_secret})
    assert payment_list.status_code == 200
    wallet_list = client.get("/api/v1/wallets", headers={"X-API-Key": first_secret})
    assert wallet_list.status_code == 403

    rotated = client.post(f"/api/v1/api-keys/{first_id}/rotate", headers=bearer)
    assert rotated.status_code == 201, rotated.text
    second_secret = rotated.json()["secret"]
    assert second_secret != first_secret
    assert client.get("/api/v1/payments", headers={"X-API-Key": first_secret}).status_code == 403
    assert client.get("/api/v1/payments", headers={"X-API-Key": second_secret}).status_code == 200

    second_id = rotated.json()["key"]["id"]
    revoked = client.delete(f"/api/v1/api-keys/{second_id}", headers=bearer)
    assert revoked.status_code == 204
    assert client.get("/api/v1/payments", headers={"X-API-Key": second_secret}).status_code == 403


def test_webhook_update_secret_rotation_and_manual_retry(
    client: TestClient, db: Session, seeded: dict[str, object]
) -> None:
    from fincore.db.models import OutboxEvent, WebhookDelivery

    merchant_token = login(client, "merchant@test.example")
    bearer = {"Authorization": f"Bearer {merchant_token['access_token']}"}
    created = client.post(
        "/api/v1/webhooks",
        headers=bearer,
        json={
            "url": "https://merchant.example/webhooks",
            "subscribed_events": ["payment.captured"],
        },
    )
    assert created.status_code == 201, created.text
    endpoint_id = created.json()["endpoint"]["id"]
    first_secret = created.json()["signing_secret"]

    disabled = client.patch(
        f"/api/v1/webhooks/{endpoint_id}",
        headers=bearer,
        json={"enabled": False},
    )
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False
    enabled = client.patch(
        f"/api/v1/webhooks/{endpoint_id}",
        headers=bearer,
        json={"enabled": True, "subscribed_events": ["payment.captured", "payment.refunded"]},
    )
    assert enabled.status_code == 200
    assert enabled.json()["enabled"] is True

    rotated = client.post(f"/api/v1/webhooks/{endpoint_id}/rotate-secret", headers=bearer)
    assert rotated.status_code == 200
    assert rotated.json()["signing_secret"] != first_secret

    merchant_org = seeded["merchant_org"]
    event = OutboxEvent(
        organization_id=merchant_org.id,  # type: ignore[attr-defined]
        event_type="payment.captured",
        resource_type="payment",
        resource_id="resource-1",
        payload={"type": "payment.captured", "data": {"id": "resource-1"}},
        deduplication_key="manual-retry-test-event",
    )
    db.add(event)
    db.flush()
    delivery = WebhookDelivery(
        endpoint_id=endpoint_id,
        outbox_event_id=event.id,
        attempt_number=6,
        status="dead_letter",
    )
    db.add(delivery)
    db.commit()

    retried = client.post(f"/api/v1/webhook-deliveries/{delivery.id}/retry", headers=bearer)
    assert retried.status_code == 200, retried.text
    assert retried.json()["status"] == "retrying"
    assert retried.json()["next_attempt_at"] is not None
