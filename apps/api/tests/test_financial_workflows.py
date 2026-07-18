import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from fincore.core.errors import InsufficientFunds, RefundExceeded
from fincore.db.models import JournalEntry, PaymentStatus, Wallet
from fincore.services.financial import (
    approve_withdrawal,
    complete_deposit,
    complete_withdrawal,
    create_deposit,
    create_payment,
    create_refund,
    create_transfer,
    request_withdrawal,
)
from fincore.services.ledger import journal_is_balanced
from fincore.services.reconciliation import run_wallet_reconciliation


def fund(db: Session, org_id: str, user_id: str, wallet_id: str, amount: int) -> None:
    deposit = create_deposit(
        db,
        organization_id=org_id,
        actor_id=user_id,
        wallet_id=wallet_id,
        amount=amount,
        currency="PKR",
        reference=f"FUND-{wallet_id}-{amount}",
    )
    complete_deposit(
        db,
        deposit_id=deposit.id,
        actor_id=user_id,
        authorized_development_confirmation=True,
    )
    db.commit()


def test_transfer_payment_refund_are_balanced(db: Session, seeded: dict[str, object]) -> None:
    customer_org = seeded["customer_org"]
    merchant_org = seeded["merchant_org"]
    customer = seeded["customer"]
    merchant = seeded["merchant"]
    customer_wallet = seeded["customer_wallet"]
    merchant_wallet = seeded["merchant_wallet"]
    fund(db, customer_org.id, customer.id, customer_wallet.id, 1_000_000)  # type: ignore[attr-defined]
    fund(db, merchant_org.id, merchant.id, merchant_wallet.id, 200_000)  # type: ignore[attr-defined]

    transfer = create_transfer(
        db,
        organization_id=customer_org.id,  # type: ignore[attr-defined]
        actor_id=customer.id,  # type: ignore[attr-defined]
        sender_wallet_id=customer_wallet.id,  # type: ignore[attr-defined]
        receiver_wallet_id=merchant_wallet.id,  # type: ignore[attr-defined]
        amount=100_000,
        currency="PKR",
        reference="TR-1",
        description="Transfer",
    )
    payment = create_payment(
        db,
        organization_id=customer_org.id,  # type: ignore[attr-defined]
        actor_id=customer.id,  # type: ignore[attr-defined]
        customer_wallet_id=customer_wallet.id,  # type: ignore[attr-defined]
        merchant_wallet_id=merchant_wallet.id,  # type: ignore[attr-defined]
        amount=250_000,
        currency="PKR",
        reference="PAY-1",
        description="Payment",
        metadata={},
    )
    refund = create_refund(
        db,
        organization_id=merchant_org.id,  # type: ignore[attr-defined]
        actor_id=merchant.id,  # type: ignore[attr-defined]
        payment_id=payment.id,
        amount=50_000,
        reason="Customer return",
    )
    db.commit()

    assert transfer.status.value == "completed"
    assert payment.status == PaymentStatus.PARTIALLY_REFUNDED
    assert refund.status.value == "completed"
    journals = db.scalars(select(JournalEntry)).all()
    assert len(journals) == 5
    assert all(journal_is_balanced(item) for item in journals)
    customer_reloaded = db.get(Wallet, customer_wallet.id)  # type: ignore[attr-defined]
    merchant_reloaded = db.get(Wallet, merchant_wallet.id)  # type: ignore[attr-defined]
    assert customer_reloaded is not None and customer_reloaded.ledger_balance == 700_000
    assert merchant_reloaded is not None and merchant_reloaded.ledger_balance == 500_000


def test_refund_cannot_exceed_capture(db: Session, seeded: dict[str, object]) -> None:
    customer_org = seeded["customer_org"]
    merchant_org = seeded["merchant_org"]
    customer = seeded["customer"]
    merchant = seeded["merchant"]
    customer_wallet = seeded["customer_wallet"]
    merchant_wallet = seeded["merchant_wallet"]
    fund(db, customer_org.id, customer.id, customer_wallet.id, 100_000)  # type: ignore[attr-defined]
    payment = create_payment(
        db,
        organization_id=customer_org.id, actor_id=customer.id,  # type: ignore[attr-defined]
        customer_wallet_id=customer_wallet.id, merchant_wallet_id=merchant_wallet.id,  # type: ignore[attr-defined]
        amount=50_000, currency="PKR", reference="P", description="", metadata={}
    )
    with pytest.raises(RefundExceeded):
        create_refund(
            db, organization_id=merchant_org.id, actor_id=merchant.id,  # type: ignore[attr-defined]
            payment_id=payment.id, amount=50_001, reason="Too much"
        )


def test_stale_concurrent_debit_cannot_overspend(db: Session, seeded: dict[str, object]) -> None:
    customer_org = seeded["customer_org"]
    customer = seeded["customer"]
    customer_wallet = seeded["customer_wallet"]
    merchant_wallet = seeded["merchant_wallet"]
    other_wallet = seeded["other_wallet"]
    fund(db, customer_org.id, customer.id, customer_wallet.id, 100_000)  # type: ignore[attr-defined]
    create_transfer(
        db, organization_id=customer_org.id, actor_id=customer.id,  # type: ignore[attr-defined]
        sender_wallet_id=customer_wallet.id, receiver_wallet_id=merchant_wallet.id,  # type: ignore[attr-defined]
        amount=80_000, currency="PKR", reference="A", description=""
    )
    db.commit()
    with pytest.raises(InsufficientFunds):
        create_transfer(
            db, organization_id=customer_org.id, actor_id=customer.id,  # type: ignore[attr-defined]
            sender_wallet_id=customer_wallet.id, receiver_wallet_id=other_wallet.id,  # type: ignore[attr-defined]
            amount=30_000, currency="PKR", reference="B", description=""
        )


def test_withdrawal_reservation_and_completion(db: Session, seeded: dict[str, object]) -> None:
    merchant_org = seeded["merchant_org"]
    merchant = seeded["merchant"]
    admin = seeded["admin"]
    platform = seeded["platform"]
    wallet = seeded["merchant_wallet"]
    fund(db, merchant_org.id, merchant.id, wallet.id, 300_000)  # type: ignore[attr-defined]
    withdrawal = request_withdrawal(
        db, organization_id=merchant_org.id, actor_id=merchant.id, wallet_id=wallet.id,  # type: ignore[attr-defined]
        amount=100_000, currency="PKR", destination_masked="•••• 1234", reference="W-1"
    )
    assert wallet.available_balance == 200_000  # type: ignore[attr-defined]
    assert wallet.reserved_balance == 100_000  # type: ignore[attr-defined]
    approve_withdrawal(
        db, withdrawal_id=withdrawal.id, reviewer_id=admin.id,  # type: ignore[attr-defined]
        reviewer_organization_id=platform.id, note="Reviewed"  # type: ignore[attr-defined]
    )
    complete_withdrawal(
        db, withdrawal_id=withdrawal.id, actor_id=admin.id,  # type: ignore[attr-defined]
        authorized_development_confirmation=True
    )
    db.commit()
    assert wallet.available_balance == 200_000  # type: ignore[attr-defined]
    assert wallet.reserved_balance == 0  # type: ignore[attr-defined]
    assert wallet.ledger_balance == 200_000  # type: ignore[attr-defined]


def test_reconciliation_detects_tampered_cache(db: Session, seeded: dict[str, object]) -> None:
    customer_org = seeded["customer_org"]
    customer = seeded["customer"]
    wallet = seeded["customer_wallet"]
    fund(db, customer_org.id, customer.id, wallet.id, 50_000)  # type: ignore[attr-defined]
    wallet.ledger_balance += 1  # type: ignore[attr-defined]
    db.commit()
    run = run_wallet_reconciliation(db)
    assert run.mismatch_count == 1


def test_transaction_limit_blocks_oversized_transfer(db: Session, seeded: dict[str, object]) -> None:
    from fincore.core.errors import TransactionLimitExceeded
    from fincore.db.models import TransactionLimit

    customer_org = seeded["customer_org"]
    customer = seeded["customer"]
    customer_wallet = seeded["customer_wallet"]
    merchant_wallet = seeded["merchant_wallet"]
    fund(db, customer_org.id, customer.id, customer_wallet.id, 200_000)  # type: ignore[attr-defined]
    db.add(
        TransactionLimit(
            organization_id=customer_org.id,  # type: ignore[attr-defined]
            operation_type="transfer",
            currency="PKR",
            minimum_amount=1,
            maximum_amount=50_000,
            daily_amount=100_000,
            monthly_amount=500_000,
        )
    )
    db.commit()

    with pytest.raises(TransactionLimitExceeded):
        create_transfer(
            db,
            organization_id=customer_org.id,  # type: ignore[attr-defined]
            actor_id=customer.id,  # type: ignore[attr-defined]
            sender_wallet_id=customer_wallet.id,  # type: ignore[attr-defined]
            receiver_wallet_id=merchant_wallet.id,  # type: ignore[attr-defined]
            amount=50_001,
            currency="PKR",
            reference="LIMIT-1",
            description="Must be rejected",
        )


def test_webhook_delivery_retries_and_dead_letters(
    db: Session, seeded: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    import httpx

    from fincore.core.crypto import encrypt_secret
    from fincore.core.security import token_hash
    from fincore.db.models import OutboxEvent, WebhookDelivery, WebhookEndpoint
    from fincore.worker.tasks import _attempt_delivery

    merchant_org = seeded["merchant_org"]
    merchant = seeded["merchant"]
    endpoint = WebhookEndpoint(
        organization_id=merchant_org.id,  # type: ignore[attr-defined]
        url="https://merchant.example/webhooks",
        subscribed_events=["payment.captured"],
        secret_hash=token_hash("signing-secret"),
        secret_encrypted=encrypt_secret("signing-secret"),
        created_by=merchant.id,  # type: ignore[attr-defined]
    )
    event = OutboxEvent(
        organization_id=merchant_org.id,  # type: ignore[attr-defined]
        event_type="payment.captured",
        resource_type="payment",
        resource_id="payment-1",
        payload={"type": "payment.captured", "data": {"id": "payment-1"}},
        deduplication_key="worker-retry-payment-1",
    )
    db.add_all([endpoint, event])
    db.flush()

    monkeypatch.setattr(
        "fincore.worker.tasks.httpx.post",
        lambda *args, **kwargs: httpx.Response(503, text="temporary outage"),
    )
    assert _attempt_delivery(db, endpoint=endpoint, event=event, attempt_number=1) is False
    first = db.scalar(
        select(WebhookDelivery).where(
            WebhookDelivery.endpoint_id == endpoint.id,
            WebhookDelivery.attempt_number == 1,
        )
    )
    assert first is not None and first.status == "retrying" and first.next_attempt_at is not None

    assert _attempt_delivery(db, endpoint=endpoint, event=event, attempt_number=6) is False
    terminal = db.scalar(
        select(WebhookDelivery).where(
            WebhookDelivery.endpoint_id == endpoint.id,
            WebhookDelivery.attempt_number == 6,
        )
    )
    assert terminal is not None and terminal.status == "dead_letter"

    monkeypatch.setattr(
        "fincore.worker.tasks.httpx.post",
        lambda *args, **kwargs: httpx.Response(204),
    )
    assert _attempt_delivery(db, endpoint=endpoint, event=event, attempt_number=7) is True
    delivered = db.scalar(
        select(WebhookDelivery).where(
            WebhookDelivery.endpoint_id == endpoint.id,
            WebhookDelivery.attempt_number == 7,
        )
    )
    assert delivered is not None and delivered.status == "delivered"
