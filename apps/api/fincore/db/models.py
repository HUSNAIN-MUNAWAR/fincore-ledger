from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fincore.db.base import Base


def uuid4_str() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class OrganizationType(StrEnum):
    PLATFORM = "platform"
    MERCHANT = "merchant"
    BUSINESS = "business"
    CUSTOMER = "customer"


class OrganizationStatus(StrEnum):
    ACTIVE = "active"
    RESTRICTED = "restricted"
    SUSPENDED = "suspended"
    CLOSED = "closed"


class VerificationStatus(StrEnum):
    NOT_STARTED = "not_started"
    PENDING = "pending"
    IN_REVIEW = "in_review"
    VERIFIED = "verified"
    REJECTED = "rejected"
    MORE_INFO = "more_information_required"
    EXPIRED = "expired"


class WalletStatus(StrEnum):
    ACTIVE = "active"
    FROZEN = "frozen"
    RESTRICTED = "restricted"
    CLOSED = "closed"


class AccountCategory(StrEnum):
    ASSET = "asset"
    LIABILITY = "liability"
    REVENUE = "revenue"
    EXPENSE = "expense"
    CLEARING = "clearing"
    SUSPENSE = "suspense"


class PostingDirection(StrEnum):
    DEBIT = "debit"
    CREDIT = "credit"


class JournalStatus(StrEnum):
    POSTED = "posted"
    REVERSED = "reversed"


class TransferStatus(StrEnum):
    CREATED = "created"
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REVERSED = "reversed"
    CANCELLED = "cancelled"


class PaymentStatus(StrEnum):
    CREATED = "created"
    REQUIRES_ACTION = "requires_action"
    PROCESSING = "processing"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    PARTIALLY_REFUNDED = "partially_refunded"
    REFUNDED = "refunded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class DepositStatus(StrEnum):
    INITIATED = "initiated"
    PENDING_PROVIDER = "pending_provider_confirmation"
    COMPLETED = "completed"
    FAILED = "failed"
    REVERSED = "reversed"


class WithdrawalStatus(StrEnum):
    REQUESTED = "requested"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"
    REVERSED = "reversed"


class RefundStatus(StrEnum):
    CREATED = "created"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ReconciliationStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ReconciliationItemStatus(StrEnum):
    OPEN = "open"
    ASSIGNED = "assigned"
    RESOLVED = "resolved"


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    type: Mapped[OrganizationType] = mapped_column(Enum(OrganizationType), nullable=False)
    status: Mapped[OrganizationStatus] = mapped_column(
        Enum(OrganizationStatus), default=OrganizationStatus.ACTIVE, nullable=False
    )
    default_currency: Mapped[str] = mapped_column(String(3), default="PKR", nullable=False)
    contact_email: Mapped[str | None] = mapped_column(String(255))
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus), default=VerificationStatus.NOT_STARTED, nullable=False
    )
    risk_level: Mapped[str] = mapped_column(String(24), default="standard", nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), default="", nullable=False)


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), default="", nullable=False)


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"))
    permission_id: Mapped[str] = mapped_column(ForeignKey("permissions.id", ondelete="CASCADE"))


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("organization_id", "user_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id"))
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    organization: Mapped[Organization] = relationship()
    user: Mapped[User] = relationship()
    role: Mapped[Role] = relationship()


class RefreshSession(Base):
    __tablename__ = "refresh_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(255))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LedgerAccount(Base):
    __tablename__ = "ledger_accounts"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", "currency"),
        CheckConstraint("length(currency) = 3", name="currency_length"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[AccountCategory] = mapped_column(Enum(AccountCategory), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    normal_balance: Mapped[PostingDirection] = mapped_column(Enum(PostingDirection), nullable=False)
    wallet_id: Mapped[str | None] = mapped_column(String(36), unique=True, index=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Wallet(Base):
    __tablename__ = "wallets"
    __table_args__ = (
        UniqueConstraint("organization_id", "currency", "wallet_type"),
        CheckConstraint("available_balance >= 0", name="available_nonnegative"),
        CheckConstraint("pending_balance >= 0", name="pending_nonnegative"),
        CheckConstraint("reserved_balance >= 0", name="reserved_nonnegative"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    wallet_type: Mapped[str] = mapped_column(String(32), default="primary", nullable=False)
    status: Mapped[WalletStatus] = mapped_column(
        Enum(WalletStatus), default=WalletStatus.ACTIVE, nullable=False
    )
    available_balance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pending_balance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reserved_balance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ledger_balance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    organization: Mapped[Organization] = relationship()


class JournalEntry(Base):
    __tablename__ = "journal_entries"
    __table_args__ = (
        UniqueConstraint("organization_id", "source_type", "source_id", "entry_kind"),
        Index("ix_journal_effective", "effective_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    reference: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[JournalStatus] = mapped_column(
        Enum(JournalStatus), default=JournalStatus.POSTED, nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    source_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    entry_kind: Mapped[str] = mapped_column(String(32), default="primary", nullable=False)
    reversal_of_id: Mapped[str | None] = mapped_column(ForeignKey("journal_entries.id"))
    correlation_id: Mapped[str | None] = mapped_column(String(64), index=True)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    postings: Mapped[list[LedgerPosting]] = relationship(
        back_populates="journal_entry", cascade="all, delete-orphan", lazy="selectin"
    )


class LedgerPosting(Base):
    __tablename__ = "ledger_postings"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        Index("ix_posting_account_created", "account_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    journal_entry_id: Mapped[str] = mapped_column(ForeignKey("journal_entries.id"), index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("ledger_accounts.id"), index=True)
    direction: Mapped[PostingDirection] = mapped_column(Enum(PostingDirection), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    memo: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    journal_entry: Mapped[JournalEntry] = relationship(back_populates="postings")
    account: Mapped[LedgerAccount] = relationship()


class Transfer(Base):
    __tablename__ = "transfers"
    __table_args__ = (CheckConstraint("amount > 0", name="amount_positive"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    sender_wallet_id: Mapped[str] = mapped_column(ForeignKey("wallets.id"), index=True)
    receiver_wallet_id: Mapped[str] = mapped_column(ForeignKey("wallets.id"), index=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    fee_amount: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reference: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    status: Mapped[TransferStatus] = mapped_column(
        Enum(TransferStatus), default=TransferStatus.CREATED, nullable=False
    )
    fee_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (CheckConstraint("amount > 0", name="amount_positive"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    merchant_organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    customer_wallet_id: Mapped[str] = mapped_column(ForeignKey("wallets.id"), index=True)
    merchant_wallet_id: Mapped[str] = mapped_column(ForeignKey("wallets.id"), index=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    fee_amount: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    refunded_amount: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reference: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus), default=PaymentStatus.CREATED, nullable=False
    )
    capture_method: Mapped[str] = mapped_column(String(24), default="automatic", nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    fee_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class PaymentEvent(Base):
    __tablename__ = "payment_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    payment_id: Mapped[str] = mapped_column(ForeignKey("payments.id"), index=True)
    previous_status: Mapped[str | None] = mapped_column(String(40))
    new_status: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Deposit(Base):
    __tablename__ = "deposits"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        UniqueConstraint("provider", "provider_reference"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    wallet_id: Mapped[str] = mapped_column(ForeignKey("wallets.id"), index=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    fee_amount: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[DepositStatus] = mapped_column(
        Enum(DepositStatus), default=DepositStatus.INITIATED, nullable=False
    )
    provider: Mapped[str] = mapped_column(String(40), default="development", nullable=False)
    provider_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reference: Mapped[str] = mapped_column(String(120), nullable=False)
    fee_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Withdrawal(Base):
    __tablename__ = "withdrawals"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        UniqueConstraint("provider", "provider_reference"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    wallet_id: Mapped[str] = mapped_column(ForeignKey("wallets.id"), index=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    fee_amount: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[WithdrawalStatus] = mapped_column(
        Enum(WithdrawalStatus), default=WithdrawalStatus.REQUESTED, nullable=False
    )
    provider: Mapped[str] = mapped_column(String(40), default="development", nullable=False)
    provider_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    destination_masked: Mapped[str] = mapped_column(String(120), nullable=False)
    reference: Mapped[str] = mapped_column(String(120), nullable=False)
    fee_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    review_note: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Refund(Base):
    __tablename__ = "refunds"
    __table_args__ = (CheckConstraint("amount > 0", name="amount_positive"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    payment_id: Mapped[str] = mapped_column(ForeignKey("payments.id"), index=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[RefundStatus] = mapped_column(
        Enum(RefundStatus), default=RefundStatus.CREATED, nullable=False
    )
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class FeeRule(Base):
    __tablename__ = "fee_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    organization_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id"), index=True)
    operation_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    fixed_amount: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    percentage_bps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    minimum_fee: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    maximum_fee: Mapped[int | None] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TransactionLimit(Base):
    __tablename__ = "transaction_limits"
    __table_args__ = (UniqueConstraint("organization_id", "operation_type", "currency"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    operation_type: Mapped[str] = mapped_column(String(40), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    minimum_amount: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    maximum_amount: Mapped[int] = mapped_column(Integer, default=100_000_000, nullable=False)
    daily_amount: Mapped[int] = mapped_column(Integer, default=250_000_000, nullable=False)
    monthly_amount: Mapped[int] = mapped_column(Integer, default=1_000_000_000, nullable=False)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("organization_id", "key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_path: Mapped[str] = mapped_column(String(180), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    response_status: Mapped[int | None] = mapped_column(Integer)
    completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    prefix: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WebhookEndpoint(Base):
    __tablename__ = "webhook_endpoints"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    subscribed_events: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    secret_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (UniqueConstraint("deduplication_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    resource_type: Mapped[str] = mapped_column(String(40), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(36), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    deduplication_key: Mapped[str] = mapped_column(String(180), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"
    __table_args__ = (UniqueConstraint("endpoint_id", "outbox_event_id", "attempt_number"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    endpoint_id: Mapped[str] = mapped_column(ForeignKey("webhook_endpoints.id"), index=True)
    outbox_event_id: Mapped[str] = mapped_column(ForeignKey("outbox_events.id"), index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="queued", nullable=False)
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_excerpt: Mapped[str | None] = mapped_column(String(500))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProviderEvent(Base):
    __tablename__ = "provider_events"
    __table_args__ = (UniqueConstraint("provider", "external_event_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    external_event_id: Mapped[str] = mapped_column(String(160), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReconciliationRun(Base):
    __tablename__ = "reconciliation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    organization_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id"), index=True)
    status: Mapped[ReconciliationStatus] = mapped_column(
        Enum(ReconciliationStatus), default=ReconciliationStatus.RUNNING, nullable=False
    )
    matched_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mismatch_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReconciliationItem(Base):
    __tablename__ = "reconciliation_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    run_id: Mapped[str] = mapped_column(ForeignKey("reconciliation_runs.id"), index=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    item_type: Mapped[str] = mapped_column(String(60), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(40), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(36), nullable=False)
    expected_amount: Mapped[int | None] = mapped_column(Integer)
    actual_amount: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str | None] = mapped_column(String(3))
    status: Mapped[ReconciliationItemStatus] = mapped_column(
        Enum(ReconciliationItemStatus), default=ReconciliationItemStatus.OPEN, nullable=False
    )
    assigned_to: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    resolution_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ComplianceReview(Base):
    __tablename__ = "compliance_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    resource_type: Mapped[str] = mapped_column(String(40), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus), default=VerificationStatus.PENDING, nullable=False
    )
    risk_flags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    assigned_to: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    decided_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_org_created", "organization_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    actor_id: Mapped[str | None] = mapped_column(String(36), index=True)
    actor_type: Mapped[str] = mapped_column(String(24), default="user", nullable=False)
    organization_id: Mapped[str | None] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    resource_type: Mapped[str] = mapped_column(String(40), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(36))
    previous_values: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    new_values: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    request_id: Mapped[str | None] = mapped_column(String(64), index=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), index=True)
    justification: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    body: Mapped[str] = mapped_column(String(500), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
