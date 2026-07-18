from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fincore.core.errors import (
    CurrencyMismatch,
    InsufficientFunds,
    NotFound,
    RefundExceeded,
    TransactionLimitExceeded,
    WalletUnavailable,
)
from fincore.db.models import (
    AccountCategory,
    Deposit,
    DepositStatus,
    FeeRule,
    Organization,
    OrganizationType,
    Payment,
    PaymentEvent,
    PaymentStatus,
    PostingDirection,
    Refund,
    RefundStatus,
    TransactionLimit,
    Transfer,
    TransferStatus,
    Wallet,
    WalletStatus,
    Withdrawal,
    WithdrawalStatus,
)
from fincore.domain.fees import FeeSnapshot, calculate_fee
from fincore.domain.states import (
    DEPOSIT_TRANSITIONS,
    PAYMENT_TRANSITIONS,
    TRANSFER_TRANSITIONS,
    WITHDRAWAL_TRANSITIONS,
    validate_transition,
)
from fincore.providers.registry import get_provider
from fincore.services.audit import record_audit
from fincore.services.ledger import (
    PostingSpec,
    ensure_system_account,
    ensure_wallet_account,
    post_journal,
)
from fincore.services.outbox import enqueue_event


def _platform_organization(db: Session) -> Organization:
    organization = db.scalar(select(Organization).where(Organization.type == OrganizationType.PLATFORM))
    if organization is None:
        raise RuntimeError("Platform organization is not configured")
    return organization


def _lock_wallet(db: Session, wallet_id: str) -> Wallet:
    wallet = db.scalar(select(Wallet).where(Wallet.id == wallet_id).with_for_update())
    if wallet is None:
        raise NotFound("Wallet")
    return wallet


def _require_active(wallet: Wallet) -> None:
    if wallet.status != WalletStatus.ACTIVE:
        raise WalletUnavailable(wallet.status.value)


def _fee_for(
    db: Session, *, organization_id: str, operation_type: str, currency: str, amount: int
) -> FeeSnapshot:
    rule = db.scalar(
        select(FeeRule)
        .where(
            FeeRule.operation_type == operation_type,
            FeeRule.currency == currency,
            FeeRule.active.is_(True),
            FeeRule.organization_id.in_([organization_id, None]),
        )
        .order_by(FeeRule.organization_id.desc())
    )
    if rule is None:
        return calculate_fee(amount)
    return calculate_fee(
        amount,
        fixed_amount=rule.fixed_amount,
        percentage_bps=rule.percentage_bps,
        minimum_fee=rule.minimum_fee,
        maximum_fee=rule.maximum_fee,
    )


def _enforce_limits(
    db: Session,
    *,
    organization_id: str,
    operation_type: str,
    currency: str,
    amount: int,
) -> None:
    rule = db.scalar(
        select(TransactionLimit).where(
            TransactionLimit.organization_id == organization_id,
            TransactionLimit.operation_type == operation_type,
            TransactionLimit.currency == currency,
        )
    )
    if rule is None:
        return
    if amount < rule.minimum_amount:
        raise TransactionLimitExceeded("minimum transaction")
    if amount > rule.maximum_amount:
        raise TransactionLimitExceeded("maximum transaction")
    now = datetime.now(UTC)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = day_start.replace(day=1)
    model_map = {
        "transfer": Transfer,
        "merchant_payment": Payment,
        "deposit": Deposit,
        "withdrawal": Withdrawal,
    }
    model: Any = model_map.get(operation_type)
    if model is None:
        return
    daily_total = int(
        db.scalar(
            select(func.coalesce(func.sum(model.amount), 0)).where(
                model.organization_id == organization_id,
                model.currency == currency,
                model.created_at >= day_start,
            )
        )
        or 0
    )
    monthly_total = int(
        db.scalar(
            select(func.coalesce(func.sum(model.amount), 0)).where(
                model.organization_id == organization_id,
                model.currency == currency,
                model.created_at >= month_start,
            )
        )
        or 0
    )
    if daily_total + amount > rule.daily_amount:
        raise TransactionLimitExceeded("daily")
    if monthly_total + amount > rule.monthly_amount:
        raise TransactionLimitExceeded("monthly")


def create_transfer(
    db: Session,
    *,
    organization_id: str,
    actor_id: str,
    sender_wallet_id: str,
    receiver_wallet_id: str,
    amount: int,
    currency: str,
    reference: str,
    description: str,
    correlation_id: str | None = None,
) -> Transfer:
    if sender_wallet_id == receiver_wallet_id:
        raise ValueError("Sender and receiver wallets must differ")
    _enforce_limits(
        db, organization_id=organization_id, operation_type="transfer", currency=currency, amount=amount
    )
    ordered = sorted([sender_wallet_id, receiver_wallet_id])
    locked = {wallet_id: _lock_wallet(db, wallet_id) for wallet_id in ordered}
    sender = locked[sender_wallet_id]
    receiver = locked[receiver_wallet_id]
    _require_active(sender)
    _require_active(receiver)
    if sender.organization_id != organization_id:
        raise NotFound("Sender wallet")
    if currency != sender.currency or currency != receiver.currency:
        raise CurrencyMismatch()
    fee = _fee_for(
        db,
        organization_id=organization_id,
        operation_type="transfer",
        currency=currency,
        amount=amount,
    )
    total = amount + fee.calculated_fee
    if sender.available_balance < total:
        raise InsufficientFunds()

    transfer = Transfer(
        organization_id=organization_id,
        sender_wallet_id=sender.id,
        receiver_wallet_id=receiver.id,
        amount=amount,
        currency=currency,
        fee_amount=fee.calculated_fee,
        reference=reference,
        description=description,
        status=TransferStatus.CREATED,
        fee_snapshot=fee.as_dict(),
        created_by=actor_id,
    )
    db.add(transfer)
    db.flush()
    validate_transition(TRANSFER_TRANSITIONS, transfer.status.value, TransferStatus.COMPLETED.value)

    sender_account = ensure_wallet_account(db, sender)
    receiver_account = ensure_wallet_account(db, receiver)
    platform = _platform_organization(db)
    fee_account = ensure_system_account(
        db,
        organization_id=platform.id,
        code="FEE-REVENUE",
        name="Platform fee revenue",
        category=AccountCategory.REVENUE,
        currency=currency,
        normal_balance=PostingDirection.CREDIT,
    )
    postings = [
        PostingSpec(sender_account.id, PostingDirection.DEBIT, total, "Sender wallet debit"),
        PostingSpec(receiver_account.id, PostingDirection.CREDIT, amount, "Receiver wallet credit"),
    ]
    if fee.calculated_fee:
        postings.append(
            PostingSpec(fee_account.id, PostingDirection.CREDIT, fee.calculated_fee, "Transfer fee")
        )
    post_journal(
        db,
        organization_id=organization_id,
        reference=reference,
        description=description or "Internal wallet transfer",
        currency=currency,
        source_type="transfer",
        source_id=transfer.id,
        postings=postings,
        correlation_id=correlation_id,
    )
    transfer.status = TransferStatus.COMPLETED
    record_audit(
        db,
        actor_id=actor_id,
        organization_id=organization_id,
        action="transfer.completed",
        resource_type="transfer",
        resource_id=transfer.id,
        new_values={"amount": amount, "fee_amount": fee.calculated_fee, "currency": currency},
        correlation_id=correlation_id,
    )
    enqueue_event(
        db,
        organization_id=organization_id,
        event_type="transfer.completed",
        resource_type="transfer",
        resource_id=transfer.id,
        data={"id": transfer.id, "amount": amount, "currency": currency, "status": transfer.status.value},
    )
    db.flush()
    return transfer


def create_payment(
    db: Session,
    *,
    organization_id: str,
    actor_id: str,
    customer_wallet_id: str,
    merchant_wallet_id: str,
    amount: int,
    currency: str,
    reference: str,
    description: str,
    metadata: dict[str, Any],
    capture_method: str = "automatic",
    correlation_id: str | None = None,
) -> Payment:
    _enforce_limits(
        db,
        organization_id=organization_id,
        operation_type="merchant_payment",
        currency=currency,
        amount=amount,
    )
    ordered = sorted([customer_wallet_id, merchant_wallet_id])
    locked = {wallet_id: _lock_wallet(db, wallet_id) for wallet_id in ordered}
    customer_wallet = locked[customer_wallet_id]
    merchant_wallet = locked[merchant_wallet_id]
    _require_active(customer_wallet)
    _require_active(merchant_wallet)
    if customer_wallet.organization_id != organization_id:
        raise NotFound("Customer wallet")
    if customer_wallet.currency != currency or merchant_wallet.currency != currency:
        raise CurrencyMismatch()
    if customer_wallet.available_balance < amount:
        raise InsufficientFunds()
    fee = _fee_for(
        db,
        organization_id=merchant_wallet.organization_id,
        operation_type="merchant_payment",
        currency=currency,
        amount=amount,
    )
    if fee.calculated_fee >= amount:
        raise ValueError("Calculated fee must be lower than payment amount")
    payment = Payment(
        organization_id=organization_id,
        merchant_organization_id=merchant_wallet.organization_id,
        customer_wallet_id=customer_wallet.id,
        merchant_wallet_id=merchant_wallet.id,
        amount=amount,
        currency=currency,
        fee_amount=fee.calculated_fee,
        reference=reference,
        description=description,
        status=PaymentStatus.CREATED,
        capture_method=capture_method,
        metadata_json=metadata,
        fee_snapshot=fee.as_dict(),
        created_by=actor_id,
    )
    db.add(payment)
    db.flush()
    db.add(PaymentEvent(payment_id=payment.id, new_status=PaymentStatus.CREATED.value))
    target = PaymentStatus.CAPTURED if capture_method == "automatic" else PaymentStatus.AUTHORIZED
    validate_transition(PAYMENT_TRANSITIONS, payment.status.value, target.value)
    if target == PaymentStatus.AUTHORIZED:
        customer_wallet.available_balance -= amount
        customer_wallet.reserved_balance += amount
        payment.status = target
    else:
        customer_account = ensure_wallet_account(db, customer_wallet)
        merchant_account = ensure_wallet_account(db, merchant_wallet)
        platform = _platform_organization(db)
        fee_account = ensure_system_account(
            db,
            organization_id=platform.id,
            code="FEE-REVENUE",
            name="Platform fee revenue",
            category=AccountCategory.REVENUE,
            currency=currency,
            normal_balance=PostingDirection.CREDIT,
        )
        postings = [
            PostingSpec(customer_account.id, PostingDirection.DEBIT, amount, "Customer payment"),
            PostingSpec(
                merchant_account.id,
                PostingDirection.CREDIT,
                amount - fee.calculated_fee,
                "Merchant proceeds",
            ),
        ]
        if fee.calculated_fee:
            postings.append(
                PostingSpec(fee_account.id, PostingDirection.CREDIT, fee.calculated_fee, "Payment fee")
            )
        post_journal(
            db,
            organization_id=organization_id,
            reference=reference,
            description=description or "Merchant wallet payment",
            currency=currency,
            source_type="payment",
            source_id=payment.id,
            postings=postings,
            correlation_id=correlation_id,
        )
        payment.status = target
    db.add(
        PaymentEvent(
            payment_id=payment.id,
            previous_status=PaymentStatus.CREATED.value,
            new_status=target.value,
        )
    )
    record_audit(
        db,
        actor_id=actor_id,
        organization_id=organization_id,
        action=f"payment.{target.value}",
        resource_type="payment",
        resource_id=payment.id,
        new_values={"amount": amount, "fee_amount": fee.calculated_fee, "currency": currency},
        correlation_id=correlation_id,
    )
    enqueue_event(
        db,
        organization_id=merchant_wallet.organization_id,
        event_type=f"payment.{target.value}",
        resource_type="payment",
        resource_id=payment.id,
        data={"id": payment.id, "amount": amount, "currency": currency, "status": target.value},
    )
    db.flush()
    return payment


def capture_payment(
    db: Session, *, payment_id: str, actor_id: str, organization_id: str
) -> Payment:
    payment = db.scalar(select(Payment).where(Payment.id == payment_id).with_for_update())
    if payment is None:
        raise NotFound("Payment")
    validate_transition(PAYMENT_TRANSITIONS, payment.status.value, PaymentStatus.CAPTURED.value)
    customer = _lock_wallet(db, payment.customer_wallet_id)
    merchant = _lock_wallet(db, payment.merchant_wallet_id)
    if customer.reserved_balance < payment.amount:
        raise InsufficientFunds()
    customer_account = ensure_wallet_account(db, customer)
    merchant_account = ensure_wallet_account(db, merchant)
    platform = _platform_organization(db)
    fee_account = ensure_system_account(
        db,
        organization_id=platform.id,
        code="FEE-REVENUE",
        name="Platform fee revenue",
        category=AccountCategory.REVENUE,
        currency=payment.currency,
        normal_balance=PostingDirection.CREDIT,
    )
    postings = [
        PostingSpec(customer_account.id, PostingDirection.DEBIT, payment.amount, "Captured payment"),
        PostingSpec(
            merchant_account.id,
            PostingDirection.CREDIT,
            payment.amount - payment.fee_amount,
            "Merchant proceeds",
        ),
    ]
    if payment.fee_amount:
        postings.append(
            PostingSpec(fee_account.id, PostingDirection.CREDIT, payment.fee_amount, "Payment fee")
        )
    post_journal(
        db,
        organization_id=organization_id,
        reference=payment.reference,
        description=payment.description or "Capture authorized payment",
        currency=payment.currency,
        source_type="payment",
        source_id=payment.id,
        postings=postings,
    )
    customer.reserved_balance -= payment.amount
    customer.available_balance += payment.amount
    previous = payment.status.value
    payment.status = PaymentStatus.CAPTURED
    db.add(PaymentEvent(payment_id=payment.id, previous_status=previous, new_status=payment.status.value))
    record_audit(
        db,
        actor_id=actor_id,
        organization_id=organization_id,
        action="payment.captured",
        resource_type="payment",
        resource_id=payment.id,
    )
    return payment


def create_refund(
    db: Session,
    *,
    organization_id: str,
    actor_id: str,
    payment_id: str,
    amount: int,
    reason: str,
    correlation_id: str | None = None,
) -> Refund:
    payment = db.scalar(select(Payment).where(Payment.id == payment_id).with_for_update())
    if payment is None:
        raise NotFound("Payment")
    if payment.status not in {PaymentStatus.CAPTURED, PaymentStatus.PARTIALLY_REFUNDED}:
        raise ValueError("Payment is not refundable")
    if amount <= 0 or payment.refunded_amount + amount > payment.amount:
        raise RefundExceeded()
    ordered = sorted([payment.customer_wallet_id, payment.merchant_wallet_id])
    locked = {wallet_id: _lock_wallet(db, wallet_id) for wallet_id in ordered}
    customer = locked[payment.customer_wallet_id]
    merchant = locked[payment.merchant_wallet_id]
    if merchant.available_balance < amount:
        raise InsufficientFunds()
    refund = Refund(
        organization_id=organization_id,
        payment_id=payment.id,
        amount=amount,
        currency=payment.currency,
        status=RefundStatus.PROCESSING,
        reason=reason,
        created_by=actor_id,
    )
    db.add(refund)
    db.flush()
    customer_account = ensure_wallet_account(db, customer)
    merchant_account = ensure_wallet_account(db, merchant)
    post_journal(
        db,
        organization_id=organization_id,
        reference=f"REF-{payment.reference}-{refund.id[:8]}",
        description=f"Refund: {reason}",
        currency=payment.currency,
        source_type="refund",
        source_id=refund.id,
        postings=[
            PostingSpec(merchant_account.id, PostingDirection.DEBIT, amount, "Merchant refund debit"),
            PostingSpec(customer_account.id, PostingDirection.CREDIT, amount, "Customer refund credit"),
        ],
        correlation_id=correlation_id,
    )
    refund.status = RefundStatus.COMPLETED
    payment.refunded_amount += amount
    previous = payment.status.value
    payment.status = (
        PaymentStatus.REFUNDED
        if payment.refunded_amount == payment.amount
        else PaymentStatus.PARTIALLY_REFUNDED
    )
    db.add(PaymentEvent(payment_id=payment.id, previous_status=previous, new_status=payment.status.value))
    record_audit(
        db,
        actor_id=actor_id,
        organization_id=organization_id,
        action="payment.refunded",
        resource_type="refund",
        resource_id=refund.id,
        new_values={"payment_id": payment.id, "amount": amount, "reason": reason},
        correlation_id=correlation_id,
    )
    enqueue_event(
        db,
        organization_id=payment.merchant_organization_id,
        event_type="payment.refunded",
        resource_type="payment",
        resource_id=payment.id,
        data={"id": payment.id, "refund_id": refund.id, "amount": amount, "status": payment.status.value},
    )
    db.flush()
    return refund


def create_deposit(
    db: Session,
    *,
    organization_id: str,
    actor_id: str,
    wallet_id: str,
    amount: int,
    currency: str,
    reference: str,
) -> Deposit:
    _enforce_limits(
        db, organization_id=organization_id, operation_type="deposit", currency=currency, amount=amount
    )
    wallet = _lock_wallet(db, wallet_id)
    _require_active(wallet)
    if wallet.organization_id != organization_id:
        raise NotFound("Wallet")
    if wallet.currency != currency:
        raise CurrencyMismatch()
    fee = _fee_for(
        db,
        organization_id=organization_id,
        operation_type="deposit",
        currency=currency,
        amount=amount,
    )
    provider = get_provider()
    result = provider.create_deposit(amount=amount, currency=currency, reference=reference)
    deposit = Deposit(
        organization_id=organization_id,
        wallet_id=wallet.id,
        amount=amount,
        currency=currency,
        fee_amount=fee.calculated_fee,
        status=DepositStatus.PENDING_PROVIDER,
        provider=provider.name,
        provider_reference=result.reference,
        reference=reference,
        fee_snapshot=fee.as_dict(),
        created_by=actor_id,
    )
    db.add(deposit)
    wallet.pending_balance += amount
    record_audit(
        db,
        actor_id=actor_id,
        organization_id=organization_id,
        action="deposit.created",
        resource_type="deposit",
        resource_id=deposit.id,
        new_values={"amount": amount, "currency": currency, "test_mode": provider.name == "development"},
    )
    db.flush()
    return deposit


def complete_deposit(
    db: Session,
    *,
    deposit_id: str,
    actor_id: str | None,
    authorized_development_confirmation: bool = False,
) -> Deposit:
    deposit = db.scalar(select(Deposit).where(Deposit.id == deposit_id).with_for_update())
    if deposit is None:
        raise NotFound("Deposit")
    validate_transition(DEPOSIT_TRANSITIONS, deposit.status.value, DepositStatus.COMPLETED.value)
    if deposit.provider == "development" and not authorized_development_confirmation:
        raise ValueError("Development deposits require an explicitly authorized test confirmation")
    wallet = _lock_wallet(db, deposit.wallet_id)
    platform = _platform_organization(db)
    wallet_account = ensure_wallet_account(db, wallet)
    clearing = ensure_system_account(
        db,
        organization_id=platform.id,
        code="DEPOSIT-CLEARING",
        name="Deposit provider clearing",
        category=AccountCategory.ASSET,
        currency=deposit.currency,
        normal_balance=PostingDirection.DEBIT,
    )
    fee_account = ensure_system_account(
        db,
        organization_id=platform.id,
        code="FEE-REVENUE",
        name="Platform fee revenue",
        category=AccountCategory.REVENUE,
        currency=deposit.currency,
        normal_balance=PostingDirection.CREDIT,
    )
    net = deposit.amount - deposit.fee_amount
    postings = [
        PostingSpec(clearing.id, PostingDirection.DEBIT, deposit.amount, "Provider funds receivable"),
        PostingSpec(wallet_account.id, PostingDirection.CREDIT, net, "Wallet deposit"),
    ]
    if deposit.fee_amount:
        postings.append(PostingSpec(fee_account.id, PostingDirection.CREDIT, deposit.fee_amount, "Deposit fee"))
    post_journal(
        db,
        organization_id=deposit.organization_id,
        reference=deposit.reference,
        description="Confirmed wallet deposit",
        currency=deposit.currency,
        source_type="deposit",
        source_id=deposit.id,
        postings=postings,
    )
    wallet.pending_balance = max(0, wallet.pending_balance - deposit.amount)
    deposit.status = DepositStatus.COMPLETED
    record_audit(
        db,
        actor_id=actor_id,
        actor_type="system" if actor_id is None else "user",
        organization_id=deposit.organization_id,
        action="deposit.completed",
        resource_type="deposit",
        resource_id=deposit.id,
        new_values={"provider_reference": deposit.provider_reference},
    )
    enqueue_event(
        db,
        organization_id=deposit.organization_id,
        event_type="deposit.completed",
        resource_type="deposit",
        resource_id=deposit.id,
        data={"id": deposit.id, "amount": deposit.amount, "currency": deposit.currency},
    )
    return deposit


def request_withdrawal(
    db: Session,
    *,
    organization_id: str,
    actor_id: str,
    wallet_id: str,
    amount: int,
    currency: str,
    destination_masked: str,
    reference: str,
) -> Withdrawal:
    _enforce_limits(
        db, organization_id=organization_id, operation_type="withdrawal", currency=currency, amount=amount
    )
    wallet = _lock_wallet(db, wallet_id)
    _require_active(wallet)
    if wallet.organization_id != organization_id:
        raise NotFound("Wallet")
    if wallet.currency != currency:
        raise CurrencyMismatch()
    fee = _fee_for(
        db,
        organization_id=organization_id,
        operation_type="withdrawal",
        currency=currency,
        amount=amount,
    )
    total = amount + fee.calculated_fee
    if wallet.available_balance < total:
        raise InsufficientFunds()
    wallet.available_balance -= total
    wallet.reserved_balance += total
    wallet.version += 1
    withdrawal = Withdrawal(
        organization_id=organization_id,
        wallet_id=wallet.id,
        amount=amount,
        currency=currency,
        fee_amount=fee.calculated_fee,
        status=WithdrawalStatus.REQUESTED,
        destination_masked=destination_masked,
        reference=reference,
        fee_snapshot=fee.as_dict(),
        created_by=actor_id,
    )
    db.add(withdrawal)
    db.flush()
    validate_transition(WITHDRAWAL_TRANSITIONS, withdrawal.status.value, WithdrawalStatus.UNDER_REVIEW.value)
    withdrawal.status = WithdrawalStatus.UNDER_REVIEW
    record_audit(
        db,
        actor_id=actor_id,
        organization_id=organization_id,
        action="withdrawal.requested",
        resource_type="withdrawal",
        resource_id=withdrawal.id,
        new_values={"amount": amount, "fee_amount": fee.calculated_fee, "currency": currency},
    )
    return withdrawal


def approve_withdrawal(
    db: Session,
    *,
    withdrawal_id: str,
    reviewer_id: str,
    reviewer_organization_id: str,
    note: str,
) -> Withdrawal:
    withdrawal = db.scalar(select(Withdrawal).where(Withdrawal.id == withdrawal_id).with_for_update())
    if withdrawal is None:
        raise NotFound("Withdrawal")
    validate_transition(WITHDRAWAL_TRANSITIONS, withdrawal.status.value, WithdrawalStatus.APPROVED.value)
    withdrawal.status = WithdrawalStatus.APPROVED
    withdrawal.reviewed_by = reviewer_id
    withdrawal.review_note = note
    provider = get_provider()
    result = provider.create_payout(
        amount=withdrawal.amount,
        currency=withdrawal.currency,
        reference=withdrawal.reference,
        destination=withdrawal.destination_masked,
    )
    validate_transition(WITHDRAWAL_TRANSITIONS, withdrawal.status.value, WithdrawalStatus.PROCESSING.value)
    withdrawal.status = WithdrawalStatus.PROCESSING
    withdrawal.provider = provider.name
    withdrawal.provider_reference = result.reference
    record_audit(
        db,
        actor_id=reviewer_id,
        organization_id=reviewer_organization_id,
        action="withdrawal.approved",
        resource_type="withdrawal",
        resource_id=withdrawal.id,
        justification=note,
        new_values={"provider_reference": result.reference, "provider_status": result.status},
    )
    return withdrawal


def complete_withdrawal(
    db: Session, *, withdrawal_id: str, actor_id: str | None, authorized_development_confirmation: bool
) -> Withdrawal:
    withdrawal = db.scalar(select(Withdrawal).where(Withdrawal.id == withdrawal_id).with_for_update())
    if withdrawal is None:
        raise NotFound("Withdrawal")
    validate_transition(WITHDRAWAL_TRANSITIONS, withdrawal.status.value, WithdrawalStatus.COMPLETED.value)
    if withdrawal.provider == "development" and not authorized_development_confirmation:
        raise ValueError("Development payouts require explicit test confirmation")
    wallet = _lock_wallet(db, withdrawal.wallet_id)
    total = withdrawal.amount + withdrawal.fee_amount
    if wallet.reserved_balance < total:
        raise InsufficientFunds()
    platform = _platform_organization(db)
    wallet_account = ensure_wallet_account(db, wallet)
    clearing = ensure_system_account(
        db,
        organization_id=platform.id,
        code="BANK-SETTLEMENT",
        name="Bank settlement asset",
        category=AccountCategory.ASSET,
        currency=withdrawal.currency,
        normal_balance=PostingDirection.DEBIT,
    )
    fee_account = ensure_system_account(
        db,
        organization_id=platform.id,
        code="FEE-REVENUE",
        name="Platform fee revenue",
        category=AccountCategory.REVENUE,
        currency=withdrawal.currency,
        normal_balance=PostingDirection.CREDIT,
    )
    postings = [
        PostingSpec(wallet_account.id, PostingDirection.DEBIT, total, "Wallet payout debit"),
        PostingSpec(clearing.id, PostingDirection.CREDIT, withdrawal.amount, "Payout settled"),
    ]
    if withdrawal.fee_amount:
        postings.append(
            PostingSpec(fee_account.id, PostingDirection.CREDIT, withdrawal.fee_amount, "Withdrawal fee")
        )
    post_journal(
        db,
        organization_id=withdrawal.organization_id,
        reference=withdrawal.reference,
        description="Completed wallet withdrawal",
        currency=withdrawal.currency,
        source_type="withdrawal",
        source_id=withdrawal.id,
        postings=postings,
    )
    wallet.reserved_balance -= total
    wallet.available_balance += total
    withdrawal.status = WithdrawalStatus.COMPLETED
    record_audit(
        db,
        actor_id=actor_id,
        actor_type="system" if actor_id is None else "user",
        organization_id=withdrawal.organization_id,
        action="withdrawal.completed",
        resource_type="withdrawal",
        resource_id=withdrawal.id,
    )
    enqueue_event(
        db,
        organization_id=withdrawal.organization_id,
        event_type="withdrawal.completed",
        resource_type="withdrawal",
        resource_id=withdrawal.id,
        data={"id": withdrawal.id, "amount": withdrawal.amount, "currency": withdrawal.currency},
    )
    return withdrawal


def reject_withdrawal(
    db: Session,
    *,
    withdrawal_id: str,
    reviewer_id: str,
    reviewer_organization_id: str,
    note: str,
) -> Withdrawal:
    withdrawal = db.scalar(select(Withdrawal).where(Withdrawal.id == withdrawal_id).with_for_update())
    if withdrawal is None:
        raise NotFound("Withdrawal")
    validate_transition(WITHDRAWAL_TRANSITIONS, withdrawal.status.value, WithdrawalStatus.REJECTED.value)
    wallet = _lock_wallet(db, withdrawal.wallet_id)
    total = withdrawal.amount + withdrawal.fee_amount
    wallet.reserved_balance -= total
    wallet.available_balance += total
    wallet.version += 1
    withdrawal.status = WithdrawalStatus.REJECTED
    withdrawal.reviewed_by = reviewer_id
    withdrawal.review_note = note
    record_audit(
        db,
        actor_id=reviewer_id,
        organization_id=reviewer_organization_id,
        action="withdrawal.rejected",
        resource_type="withdrawal",
        resource_id=withdrawal.id,
        justification=note,
    )
    return withdrawal
