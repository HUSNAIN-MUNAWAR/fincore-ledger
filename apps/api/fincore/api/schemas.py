from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RegisterRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=160)
    password: str = Field(min_length=12, max_length=128)
    organization_name: str = Field(min_length=2, max_length=160)
    currency: str = "PKR"

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        value = value.upper()
        if len(value) != 3:
            raise ValueError("Currency must contain 3 letters")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    organization_id: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    organization_id: str
    permissions: list[str]


class UserView(ORMModel):
    id: str
    email: str
    full_name: str
    status: str
    email_verified: bool
    created_at: datetime


class OrganizationView(ORMModel):
    id: str
    name: str
    type: Any
    status: Any
    default_currency: str
    verification_status: Any
    risk_level: str
    created_at: datetime


class WalletView(ORMModel):
    id: str
    organization_id: str
    currency: str
    wallet_type: str
    status: Any
    available_balance: int
    pending_balance: int
    reserved_balance: int
    ledger_balance: int
    version: int
    created_at: datetime
    updated_at: datetime


class TransferCreate(BaseModel):
    sender_wallet_id: str
    receiver_wallet_id: str
    amount: int = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    reference: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=255)


class TransferView(ORMModel):
    id: str
    organization_id: str
    sender_wallet_id: str
    receiver_wallet_id: str
    amount: int
    currency: str
    fee_amount: int
    reference: str
    description: str
    status: Any
    fee_snapshot: dict[str, Any]
    created_at: datetime


class PaymentCreate(BaseModel):
    customer_wallet_id: str
    merchant_wallet_id: str
    amount: int = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    reference: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=255)
    metadata: dict[str, Any] = Field(default_factory=dict)
    capture_method: str = Field(default="automatic", pattern="^(automatic|manual)$")


class PaymentView(ORMModel):
    id: str
    organization_id: str
    merchant_organization_id: str
    customer_wallet_id: str
    merchant_wallet_id: str
    amount: int
    currency: str
    fee_amount: int
    refunded_amount: int
    reference: str
    description: str
    status: Any
    capture_method: str
    metadata_json: dict[str, Any]
    fee_snapshot: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class RefundCreate(BaseModel):
    amount: int = Field(gt=0)
    reason: str = Field(min_length=3, max_length=255)


class RefundView(ORMModel):
    id: str
    organization_id: str
    payment_id: str
    amount: int
    currency: str
    status: Any
    reason: str
    created_at: datetime


class DepositCreate(BaseModel):
    wallet_id: str
    amount: int = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    reference: str = Field(min_length=1, max_length=120)


class DepositView(ORMModel):
    id: str
    wallet_id: str
    amount: int
    currency: str
    fee_amount: int
    status: Any
    provider: str
    provider_reference: str | None
    reference: str
    created_at: datetime


class WithdrawalCreate(BaseModel):
    wallet_id: str
    amount: int = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    destination_masked: str = Field(min_length=4, max_length=120)
    reference: str = Field(min_length=1, max_length=120)


class WithdrawalDecision(BaseModel):
    note: str = Field(min_length=3, max_length=500)


class WithdrawalView(ORMModel):
    id: str
    organization_id: str
    wallet_id: str
    amount: int
    currency: str
    fee_amount: int
    status: Any
    provider: str
    provider_reference: str | None
    destination_masked: str
    reference: str
    review_note: str | None
    created_at: datetime
    updated_at: datetime


class PostingView(ORMModel):
    id: str
    account_id: str
    direction: Any
    amount: int
    memo: str
    created_at: datetime


class JournalView(ORMModel):
    id: str
    organization_id: str
    reference: str
    description: str
    currency: str
    status: Any
    source_type: str
    source_id: str
    entry_kind: str
    reversal_of_id: str | None
    correlation_id: str | None
    effective_at: datetime
    created_at: datetime
    postings: list[PostingView]
    balanced: bool | None = None


class WebhookCreate(BaseModel):
    url: str = Field(pattern="^https?://", max_length=500)
    subscribed_events: list[str] = Field(min_length=1)


class WebhookUpdate(BaseModel):
    url: str | None = Field(default=None, pattern="^https?://", max_length=500)
    subscribed_events: list[str] | None = Field(default=None, min_length=1)
    enabled: bool | None = None


class WebhookView(ORMModel):
    id: str
    organization_id: str
    url: str
    subscribed_events: list[str]
    enabled: bool
    created_at: datetime


class WebhookCreated(BaseModel):
    endpoint: WebhookView
    signing_secret: str


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    scopes: list[str] = Field(min_length=1)
    expires_at: datetime | None = None


class ApiKeyView(ORMModel):
    id: str
    name: str
    prefix: str
    scopes: list[str]
    expires_at: datetime | None
    last_used_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class ApiKeyCreated(BaseModel):
    key: ApiKeyView
    secret: str


class ReconciliationRunView(ORMModel):
    id: str
    organization_id: str | None
    status: Any
    matched_count: int
    mismatch_count: int
    started_at: datetime
    completed_at: datetime | None


class AuditView(ORMModel):
    id: str
    actor_id: str | None
    actor_type: str
    organization_id: str | None
    action: str
    resource_type: str
    resource_id: str | None
    previous_values: dict[str, Any] | None
    new_values: dict[str, Any] | None
    justification: str | None
    created_at: datetime


class DashboardSummary(BaseModel):
    wallet_count: int
    available_balance: int
    pending_balance: int
    reserved_balance: int
    payment_count: int
    payment_volume: int
    refund_volume: int
    transfer_count: int
    withdrawal_pending_count: int
    currency: str


class Paginated(BaseModel):
    items: list[Any]
    total: int
    page: int
    page_size: int
