from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from fincore.core.crypto import encrypt_secret
from fincore.core.security import generate_signing_secret, hash_password, token_hash
from fincore.db.models import (
    FeeRule,
    Membership,
    Organization,
    OrganizationType,
    Payment,
    Refund,
    Role,
    User,
    VerificationStatus,
    Wallet,
    WebhookEndpoint,
    Withdrawal,
)
from fincore.db.session import SessionLocal
from fincore.services.bootstrap import ensure_rbac
from fincore.services.financial import (
    complete_deposit,
    create_deposit,
    create_payment,
    create_refund,
    request_withdrawal,
)
from fincore.services.ledger import ensure_wallet_account
from fincore.services.reconciliation import run_wallet_reconciliation

PASSWORD = "FinCore-Dev-2026!"
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SAMPLE_PATH = REPO_ROOT / "data" / "sample" / "uci_online_retail_payments.json"


@dataclass(frozen=True)
class PublicDatasetSeedSummary:
    payments_created: int
    refunds_created: int
    withdrawals_created: int
    reconciliation_matched: int
    reconciliation_mismatches: int
    total_payment_minor_units: int
    sample_path: Path


def _load_sample(path: Path) -> dict[str, Any]:
    payload = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    if not payload.get("payments"):
        raise ValueError(f"No payment records found in public dataset sample: {path}")
    for record in payload["payments"]:
        for field in ["payment_reference", "amount_minor", "currency", "invoice_no"]:
            if field not in record:
                raise ValueError(f"Dataset payment record is missing {field}: {record}")
        if int(record["amount_minor"]) <= 0:
            raise ValueError(f"Dataset payment amount must be positive: {record}")
    return payload


def _organization(db: Session, *, name: str, type_: OrganizationType, currency: str, email: str | None) -> Organization:
    organization = db.scalar(select(Organization).where(Organization.name == name))
    if organization:
        return organization
    organization = Organization(
        name=name,
        type=type_,
        default_currency=currency,
        contact_email=email,
        verification_status=VerificationStatus.VERIFIED,
        metadata_json={"demo_dataset": "uci_online_retail"},
    )
    db.add(organization)
    db.flush()
    return organization


def _user(db: Session, *, email: str, full_name: str) -> User:
    user = db.scalar(select(User).where(User.email == email))
    if user:
        return user
    user = User(email=email, full_name=full_name, password_hash=hash_password(PASSWORD), email_verified=True)
    db.add(user)
    db.flush()
    return user


def _membership(db: Session, *, organization: Organization, user: User, role_name: str) -> None:
    role = db.scalar(select(Role).where(Role.name == role_name))
    if role is None:
        raise RuntimeError(f"RBAC role is missing: {role_name}")
    exists = db.scalar(
        select(Membership).where(
            Membership.organization_id == organization.id,
            Membership.user_id == user.id,
            Membership.role_id == role.id,
        )
    )
    if not exists:
        db.add(Membership(organization_id=organization.id, user_id=user.id, role_id=role.id))


def _wallet(db: Session, *, organization: Organization, currency: str) -> Wallet:
    wallet = db.scalar(
        select(Wallet).where(
            Wallet.organization_id == organization.id,
            Wallet.currency == currency,
            Wallet.wallet_type == "primary",
        )
    )
    if wallet:
        return wallet
    wallet = Wallet(organization_id=organization.id, currency=currency)
    db.add(wallet)
    db.flush()
    ensure_wallet_account(db, wallet)
    return wallet


def _fee_rule(
    db: Session,
    *,
    operation_type: str,
    currency: str,
    fixed_amount: int = 0,
    percentage_bps: int = 0,
    minimum_fee: int = 0,
) -> None:
    exists = db.scalar(
        select(FeeRule).where(
            FeeRule.organization_id.is_(None),
            FeeRule.operation_type == operation_type,
            FeeRule.currency == currency,
            FeeRule.active.is_(True),
        )
    )
    if not exists:
        db.add(
            FeeRule(
                organization_id=None,
                operation_type=operation_type,
                currency=currency,
                fixed_amount=fixed_amount,
                percentage_bps=percentage_bps,
                minimum_fee=minimum_fee,
            )
        )


def _ensure_webhook(db: Session, *, merchant: Organization, user: User) -> None:
    exists = db.scalar(select(WebhookEndpoint).where(WebhookEndpoint.organization_id == merchant.id))
    if exists:
        return
    secret = generate_signing_secret()
    db.add(
        WebhookEndpoint(
            organization_id=merchant.id,
            url="https://merchant.example/webhooks/uci-online-retail",
            subscribed_events=["payment.captured", "payment.refunded", "withdrawal.completed"],
            secret_hash=token_hash(secret),
            secret_encrypted=encrypt_secret(secret),
            created_by=user.id,
        )
    )


def seed_public_dataset(db: Session, sample_path: Path = DEFAULT_SAMPLE_PATH) -> PublicDatasetSeedSummary:
    payload = _load_sample(sample_path)
    currency = payload["payments"][0]["currency"]
    ensure_rbac(db)

    platform = _organization(
        db,
        name="FinCore Platform",
        type_=OrganizationType.PLATFORM,
        currency=currency,
        email=None,
    )
    customer_org = _organization(
        db,
        name="UCI Online Retail Customer Cohort",
        type_=OrganizationType.CUSTOMER,
        currency=currency,
        email="customer@fincore.example",
    )
    merchant_org = _organization(
        db,
        name="UCI Online Retail Demo Merchant",
        type_=OrganizationType.MERCHANT,
        currency=currency,
        email="merchant@fincore.example",
    )
    users = {
        "admin": _user(db, email="admin@fincore.example", full_name="Platform Admin"),
        "ops": _user(db, email="ops@fincore.example", full_name="Operations Reviewer"),
        "merchant": _user(db, email="merchant@fincore.example", full_name="UCI Retail Merchant"),
        "customer": _user(db, email="customer@fincore.example", full_name="Public Dataset Customer"),
    }
    _membership(db, organization=platform, user=users["admin"], role_name="platform_administrator")
    _membership(db, organization=platform, user=users["ops"], role_name="operations_manager")
    _membership(db, organization=merchant_org, user=users["merchant"], role_name="merchant_administrator")
    _membership(db, organization=customer_org, user=users["customer"], role_name="customer")

    _fee_rule(db, operation_type="merchant_payment", currency=currency, percentage_bps=250, minimum_fee=25)
    _fee_rule(db, operation_type="transfer", currency=currency, fixed_amount=10)
    _fee_rule(db, operation_type="withdrawal", currency=currency, fixed_amount=50)
    _fee_rule(db, operation_type="deposit", currency=currency)
    db.flush()

    customer_wallet = _wallet(db, organization=customer_org, currency=currency)
    merchant_wallet = _wallet(db, organization=merchant_org, currency=currency)

    total_payments = sum(int(record["amount_minor"]) for record in payload["payments"])
    funding_reference = "UCI-CUSTOMER-FUNDING"
    if not db.scalar(select(Payment).where(Payment.reference == payload["payments"][0]["payment_reference"])):
        deposit = create_deposit(
            db,
            organization_id=customer_org.id,
            actor_id=users["customer"].id,
            wallet_id=customer_wallet.id,
            amount=total_payments + 50_000,
            currency=currency,
            reference=funding_reference,
        )
        complete_deposit(
            db,
            deposit_id=deposit.id,
            actor_id=users["admin"].id,
            authorized_development_confirmation=True,
        )

    payments_created = 0
    for record in payload["payments"]:
        if db.scalar(select(Payment).where(Payment.reference == record["payment_reference"])):
            continue
        create_payment(
            db,
            organization_id=customer_org.id,
            actor_id=users["customer"].id,
            customer_wallet_id=customer_wallet.id,
            merchant_wallet_id=merchant_wallet.id,
            amount=int(record["amount_minor"]),
            currency=record["currency"],
            reference=record["payment_reference"],
            description=record["description"],
            metadata={
                "dataset": "uci_online_retail",
                "invoice_no": record["invoice_no"],
                "invoice_date": record["invoice_date"],
                "customer_id": record["customer_id"],
                "country": record["country"],
                "line_count": record["line_count"],
                "item_count": record["item_count"],
                "sample_line_items": record["sample_line_items"],
            },
        )
        payments_created += 1

    refunds_created = 0
    for refund_record in payload.get("refunds", []):
        payment = db.scalar(select(Payment).where(Payment.reference == refund_record["payment_reference"]))
        if payment is None:
            continue
        already_refunded = db.scalar(select(Refund).where(Refund.payment_id == payment.id))
        if already_refunded:
            continue
        create_refund(
            db,
            organization_id=customer_org.id,
            actor_id=users["merchant"].id,
            payment_id=payment.id,
            amount=int(refund_record["amount_minor"]),
            reason=refund_record["reason"],
        )
        refunds_created += 1

    _ensure_webhook(db, merchant=merchant_org, user=users["merchant"])

    withdrawals_created = 0
    if not db.scalar(select(Withdrawal).where(Withdrawal.reference == "UCI-PAYOUT-SAMPLE-001")):
        request_withdrawal(
            db,
            organization_id=merchant_org.id,
            actor_id=users["merchant"].id,
            wallet_id=merchant_wallet.id,
            amount=min(150_000, max(10_000, merchant_wallet.available_balance // 5)),
            currency=currency,
            destination_masked="Dataset settlement account **** 2010",
            reference="UCI-PAYOUT-SAMPLE-001",
        )
        withdrawals_created += 1

    run = run_wallet_reconciliation(db)
    db.commit()
    return PublicDatasetSeedSummary(
        payments_created=payments_created,
        refunds_created=refunds_created,
        withdrawals_created=withdrawals_created,
        reconciliation_matched=run.matched_count,
        reconciliation_mismatches=run.mismatch_count,
        total_payment_minor_units=total_payments,
        sample_path=sample_path,
    )


def main() -> None:
    with SessionLocal() as db:
        summary = seed_public_dataset(db)
    print("FinCore public dataset demo data created.")
    print(f"Dataset sample: {summary.sample_path}")
    print(f"Payments created: {summary.payments_created}")
    print(f"Refunds created: {summary.refunds_created}")
    print(f"Withdrawals created: {summary.withdrawals_created}")
    print(f"Reconciliation: {summary.reconciliation_matched} matched, {summary.reconciliation_mismatches} mismatches")
    print(f"Password for all development accounts: {PASSWORD}")
    print("Accounts: admin@fincore.example, ops@fincore.example, merchant@fincore.example, customer@fincore.example")


if __name__ == "__main__":
    main()
