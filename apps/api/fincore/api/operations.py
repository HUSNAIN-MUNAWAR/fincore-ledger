from __future__ import annotations

import csv
import hashlib
import io
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from fincore.api.deps import Principal, require_permission
from fincore.api.schemas import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyView,
    AuditView,
    DashboardSummary,
    JournalView,
    ReconciliationRunView,
    WebhookCreate,
    WebhookCreated,
    WebhookUpdate,
    WebhookView,
    WithdrawalDecision,
    WithdrawalView,
)
from fincore.core.crypto import encrypt_secret
from fincore.core.errors import DomainError, NotFound
from fincore.core.security import generate_signing_secret, new_api_key, token_hash
from fincore.db.models import (
    ApiKey,
    AuditLog,
    JournalEntry,
    Payment,
    ProviderEvent,
    ReconciliationItem,
    ReconciliationRun,
    Refund,
    Transfer,
    Wallet,
    WebhookDelivery,
    WebhookEndpoint,
    Withdrawal,
    WithdrawalStatus,
)
from fincore.db.session import get_db
from fincore.providers.registry import get_provider
from fincore.services.audit import record_audit
from fincore.services.financial import (
    approve_withdrawal,
    complete_deposit,
    complete_withdrawal,
    reject_withdrawal,
)
from fincore.services.ledger import journal_is_balanced
from fincore.services.reconciliation import run_wallet_reconciliation

router = APIRouter(tags=["Operations and administration"])


@router.get("/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("wallets.read"))],
) -> DashboardSummary:
    wallets = db.scalars(select(Wallet).where(Wallet.organization_id == principal.organization_id)).all()
    currency = wallets[0].currency if wallets else "PKR"
    payment_filter = or_(
        Payment.organization_id == principal.organization_id,
        Payment.merchant_organization_id == principal.organization_id,
    )
    payment_count = int(db.scalar(select(func.count(Payment.id)).where(payment_filter)) or 0)
    payment_volume = int(db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(payment_filter)) or 0)
    refund_volume = int(
        db.scalar(
            select(func.coalesce(func.sum(Refund.amount), 0))
            .join(Payment, Payment.id == Refund.payment_id)
            .where(payment_filter)
        )
        or 0
    )
    transfer_count = int(
        db.scalar(
            select(func.count(Transfer.id)).where(Transfer.organization_id == principal.organization_id)
        )
        or 0
    )
    pending_withdrawals = int(
        db.scalar(
            select(func.count(Withdrawal.id)).where(
                Withdrawal.organization_id == principal.organization_id,
                Withdrawal.status.in_(
                    [
                        WithdrawalStatus.REQUESTED,
                        WithdrawalStatus.UNDER_REVIEW,
                        WithdrawalStatus.APPROVED,
                        WithdrawalStatus.PROCESSING,
                    ]
                ),
            )
        )
        or 0
    )
    return DashboardSummary(
        wallet_count=len(wallets),
        available_balance=sum(item.available_balance for item in wallets),
        pending_balance=sum(item.pending_balance for item in wallets),
        reserved_balance=sum(item.reserved_balance for item in wallets),
        payment_count=payment_count,
        payment_volume=payment_volume,
        refund_volume=refund_volume,
        transfer_count=transfer_count,
        withdrawal_pending_count=pending_withdrawals,
        currency=currency,
    )


@router.get("/ledger/journals", response_model=list[JournalView])
def list_journals(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("ledger.read"))],
    source_type: str | None = None,
    reference: str | None = None,
) -> list[dict[str, Any]]:
    query = (
        select(JournalEntry)
        .options(selectinload(JournalEntry.postings))
        .order_by(JournalEntry.created_at.desc())
        .limit(200)
    )
    if source_type:
        query = query.where(JournalEntry.source_type == source_type)
    if reference:
        query = query.where(JournalEntry.reference.ilike(f"%{reference}%"))
    journals = db.scalars(query).unique().all()
    result: list[dict[str, Any]] = []
    for journal in journals:
        value = JournalView.model_validate(journal).model_dump(mode="json")
        value["balanced"] = journal_is_balanced(journal)
        result.append(value)
    return result


@router.get("/ledger/journals/{journal_id}", response_model=JournalView)
def get_journal(
    journal_id: str,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("ledger.read"))],
) -> dict[str, Any]:
    journal = db.scalar(
        select(JournalEntry)
        .options(selectinload(JournalEntry.postings))
        .where(JournalEntry.id == journal_id)
    )
    if journal is None:
        raise NotFound("Journal entry")
    value = JournalView.model_validate(journal).model_dump(mode="json")
    value["balanced"] = journal_is_balanced(journal)
    return value


@router.post("/reconciliation/runs", response_model=ReconciliationRunView, status_code=201)
def reconciliation_run(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("reconciliation.manage"))],
) -> ReconciliationRun:
    run = run_wallet_reconciliation(db)
    record_audit(
        db,
        actor_id=principal.user_id,
        organization_id=principal.organization_id,
        action="reconciliation.completed",
        resource_type="reconciliation_run",
        resource_id=run.id,
        new_values={"matched": run.matched_count, "mismatches": run.mismatch_count},
    )
    db.commit()
    return run


@router.get("/reconciliation/runs", response_model=list[ReconciliationRunView])
def list_reconciliation_runs(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("ledger.read"))],
) -> list[ReconciliationRun]:
    return list(
        db.scalars(select(ReconciliationRun).order_by(ReconciliationRun.started_at.desc()).limit(50)).all()
    )


@router.get("/reconciliation/items")
def list_reconciliation_items(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("ledger.read"))],
) -> list[dict[str, Any]]:
    items = db.scalars(
        select(ReconciliationItem).order_by(ReconciliationItem.created_at.desc()).limit(200)
    ).all()
    return [
        {
            "id": item.id,
            "run_id": item.run_id,
            "item_type": item.item_type,
            "resource_type": item.resource_type,
            "resource_id": item.resource_id,
            "expected_amount": item.expected_amount,
            "actual_amount": item.actual_amount,
            "currency": item.currency,
            "status": item.status.value,
            "resolution_note": item.resolution_note,
            "created_at": item.created_at,
        }
        for item in items
    ]


@router.post("/withdrawals/{withdrawal_id}/approve", response_model=WithdrawalView)
def approve(
    withdrawal_id: str,
    payload: WithdrawalDecision,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("withdrawals.review"))],
) -> Withdrawal:
    item = approve_withdrawal(
        db,
        withdrawal_id=withdrawal_id,
        reviewer_id=principal.user_id,
        reviewer_organization_id=principal.organization_id,
        note=payload.note,
    )
    db.commit()
    return item


@router.post("/withdrawals/{withdrawal_id}/reject", response_model=WithdrawalView)
def reject(
    withdrawal_id: str,
    payload: WithdrawalDecision,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("withdrawals.review"))],
) -> Withdrawal:
    item = reject_withdrawal(
        db,
        withdrawal_id=withdrawal_id,
        reviewer_id=principal.user_id,
        reviewer_organization_id=principal.organization_id,
        note=payload.note,
    )
    db.commit()
    return item


@router.post("/development/deposits/{deposit_id}/confirm", status_code=200)
def confirm_development_deposit(
    deposit_id: str,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("wallets.manage"))],
) -> dict[str, str]:
    item = complete_deposit(
        db,
        deposit_id=deposit_id,
        actor_id=principal.user_id,
        authorized_development_confirmation=True,
    )
    db.commit()
    return {"id": item.id, "status": item.status.value, "test_mode": "true"}


@router.post("/development/withdrawals/{withdrawal_id}/confirm", status_code=200)
def confirm_development_withdrawal(
    withdrawal_id: str,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("withdrawals.review"))],
) -> dict[str, str]:
    item = complete_withdrawal(
        db,
        withdrawal_id=withdrawal_id,
        actor_id=principal.user_id,
        authorized_development_confirmation=True,
    )
    db.commit()
    return {"id": item.id, "status": item.status.value, "test_mode": "true"}


@router.post("/webhooks", response_model=WebhookCreated, status_code=201)
def create_webhook(
    payload: WebhookCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("webhooks.manage"))],
) -> WebhookCreated:
    secret = generate_signing_secret()
    endpoint = WebhookEndpoint(
        organization_id=principal.organization_id,
        url=payload.url,
        subscribed_events=payload.subscribed_events,
        secret_hash=token_hash(secret),
        secret_encrypted=encrypt_secret(secret),
        created_by=principal.user_id,
    )
    db.add(endpoint)
    db.flush()
    record_audit(
        db,
        actor_id=principal.user_id,
        organization_id=principal.organization_id,
        action="webhook.created",
        resource_type="webhook_endpoint",
        resource_id=endpoint.id,
        new_values={"url": endpoint.url, "events": endpoint.subscribed_events},
    )
    db.commit()
    return WebhookCreated(endpoint=WebhookView.model_validate(endpoint), signing_secret=secret)


@router.patch("/webhooks/{endpoint_id}", response_model=WebhookView)
def update_webhook(
    endpoint_id: str,
    payload: WebhookUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("webhooks.manage"))],
) -> WebhookEndpoint:
    endpoint = db.scalar(
        select(WebhookEndpoint).where(
            WebhookEndpoint.id == endpoint_id,
            WebhookEndpoint.organization_id == principal.organization_id,
        )
    )
    if endpoint is None:
        raise NotFound("Webhook endpoint")
    previous = {
        "url": endpoint.url,
        "events": endpoint.subscribed_events,
        "enabled": endpoint.enabled,
    }
    if payload.url is not None:
        endpoint.url = payload.url
    if payload.subscribed_events is not None:
        endpoint.subscribed_events = payload.subscribed_events
    if payload.enabled is not None:
        endpoint.enabled = payload.enabled
    record_audit(
        db,
        actor_id=principal.user_id,
        organization_id=principal.organization_id,
        action="webhook.updated",
        resource_type="webhook_endpoint",
        resource_id=endpoint.id,
        previous_values=previous,
        new_values={
            "url": endpoint.url,
            "events": endpoint.subscribed_events,
            "enabled": endpoint.enabled,
        },
    )
    db.commit()
    return endpoint


@router.post("/webhooks/{endpoint_id}/rotate-secret", response_model=WebhookCreated)
def rotate_webhook_secret(
    endpoint_id: str,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("webhooks.manage"))],
) -> WebhookCreated:
    endpoint = db.scalar(
        select(WebhookEndpoint).where(
            WebhookEndpoint.id == endpoint_id,
            WebhookEndpoint.organization_id == principal.organization_id,
        )
    )
    if endpoint is None:
        raise NotFound("Webhook endpoint")
    secret = generate_signing_secret()
    endpoint.secret_hash = token_hash(secret)
    endpoint.secret_encrypted = encrypt_secret(secret)
    record_audit(
        db,
        actor_id=principal.user_id,
        organization_id=principal.organization_id,
        action="webhook.secret_rotated",
        resource_type="webhook_endpoint",
        resource_id=endpoint.id,
    )
    db.commit()
    return WebhookCreated(endpoint=WebhookView.model_validate(endpoint), signing_secret=secret)


@router.get("/webhooks", response_model=list[WebhookView])
def list_webhooks(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("webhooks.manage"))],
) -> list[WebhookEndpoint]:
    return list(
        db.scalars(
            select(WebhookEndpoint)
            .where(WebhookEndpoint.organization_id == principal.organization_id)
            .order_by(WebhookEndpoint.created_at.desc())
        ).all()
    )


@router.get("/webhook-deliveries")
def list_webhook_deliveries(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("webhooks.manage"))],
) -> list[dict[str, Any]]:
    rows = db.execute(
        select(WebhookDelivery, WebhookEndpoint)
        .join(WebhookEndpoint, WebhookEndpoint.id == WebhookDelivery.endpoint_id)
        .where(WebhookEndpoint.organization_id == principal.organization_id)
        .order_by(WebhookDelivery.created_at.desc())
        .limit(100)
    ).all()
    return [
        {
            "id": delivery.id,
            "endpoint_url": endpoint.url,
            "attempt_number": delivery.attempt_number,
            "status": delivery.status,
            "response_status": delivery.response_status,
            "next_attempt_at": delivery.next_attempt_at,
            "delivered_at": delivery.delivered_at,
            "created_at": delivery.created_at,
        }
        for delivery, endpoint in rows
    ]


@router.post("/webhook-deliveries/{delivery_id}/retry")
def retry_webhook_delivery(
    delivery_id: str,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("webhooks.manage"))],
) -> dict[str, Any]:
    row = db.execute(
        select(WebhookDelivery, WebhookEndpoint)
        .join(WebhookEndpoint, WebhookEndpoint.id == WebhookDelivery.endpoint_id)
        .where(
            WebhookDelivery.id == delivery_id,
            WebhookEndpoint.organization_id == principal.organization_id,
        )
    ).first()
    if row is None:
        raise NotFound("Webhook delivery")
    delivery, endpoint = row
    if delivery.status == "delivered":
        raise ValueError("Delivered webhooks cannot be retried")
    if not endpoint.enabled:
        raise ValueError("Enable the webhook endpoint before retrying a delivery")
    delivery.status = "retrying"
    delivery.next_attempt_at = datetime.now(UTC)
    record_audit(
        db,
        actor_id=principal.user_id,
        organization_id=principal.organization_id,
        action="webhook.delivery_retry_requested",
        resource_type="webhook_delivery",
        resource_id=delivery.id,
        new_values={"attempt_number": delivery.attempt_number},
    )
    db.commit()
    return {
        "id": delivery.id,
        "status": delivery.status,
        "next_attempt_at": delivery.next_attempt_at,
    }


@router.post("/api-keys", response_model=ApiKeyCreated, status_code=201)
def create_api_key(
    payload: ApiKeyCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("api_keys.manage"))],
) -> ApiKeyCreated:
    prefix, secret = new_api_key()
    if any(scope not in principal.permissions for scope in payload.scopes):
        raise ValueError("API key scopes must be a subset of the creator permissions")
    item = ApiKey(
        organization_id=principal.organization_id,
        name=payload.name,
        prefix=prefix,
        key_hash=token_hash(secret),
        scopes=payload.scopes,
        expires_at=payload.expires_at,
        created_by=principal.user_id,
    )
    db.add(item)
    db.flush()
    record_audit(
        db,
        actor_id=principal.user_id,
        organization_id=principal.organization_id,
        action="api_key.created",
        resource_type="api_key",
        resource_id=item.id,
        new_values={"name": item.name, "prefix": item.prefix, "scopes": item.scopes},
    )
    db.commit()
    return ApiKeyCreated(key=ApiKeyView.model_validate(item), secret=secret)


@router.get("/api-keys", response_model=list[ApiKeyView])
def list_api_keys(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("api_keys.manage"))],
) -> list[ApiKey]:
    return list(
        db.scalars(
            select(ApiKey)
            .where(ApiKey.organization_id == principal.organization_id)
            .order_by(ApiKey.created_at.desc())
        ).all()
    )


@router.post("/api-keys/{key_id}/rotate", response_model=ApiKeyCreated, status_code=201)
def rotate_api_key(
    key_id: str,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("api_keys.manage"))],
) -> ApiKeyCreated:
    current = db.scalar(
        select(ApiKey).where(
            ApiKey.id == key_id,
            ApiKey.organization_id == principal.organization_id,
            ApiKey.revoked_at.is_(None),
        )
    )
    if current is None:
        raise NotFound("API key")
    prefix, secret = new_api_key()
    replacement = ApiKey(
        organization_id=current.organization_id,
        name=current.name,
        prefix=prefix,
        key_hash=token_hash(secret),
        scopes=current.scopes,
        expires_at=current.expires_at,
        created_by=principal.user_id,
    )
    current.revoked_at = datetime.now(UTC)
    db.add(replacement)
    db.flush()
    record_audit(
        db,
        actor_id=principal.user_id,
        organization_id=principal.organization_id,
        action="api_key.rotated",
        resource_type="api_key",
        resource_id=replacement.id,
        previous_values={"key_id": current.id, "prefix": current.prefix},
        new_values={"key_id": replacement.id, "prefix": replacement.prefix},
    )
    db.commit()
    return ApiKeyCreated(key=ApiKeyView.model_validate(replacement), secret=secret)


@router.delete("/api-keys/{key_id}", status_code=204)
def revoke_api_key(
    key_id: str,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("api_keys.manage"))],
) -> None:
    item = db.scalar(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.organization_id == principal.organization_id)
    )
    if item is None:
        raise NotFound("API key")
    item.revoked_at = datetime.now(UTC)
    record_audit(
        db,
        actor_id=principal.user_id,
        organization_id=principal.organization_id,
        action="api_key.revoked",
        resource_type="api_key",
        resource_id=item.id,
    )
    db.commit()


@router.get("/audit-logs", response_model=list[AuditView])
def list_audit_logs(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("audit.read"))],
) -> list[AuditLog]:
    return list(
        db.scalars(
            select(AuditLog)
            .where(
                or_(
                    AuditLog.organization_id == principal.organization_id,
                    AuditLog.organization_id.is_(None),
                )
            )
            .order_by(AuditLog.created_at.desc())
            .limit(200)
        ).all()
    )


@router.get("/reports/transactions.csv")
def export_transactions(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("reports.export"))],
) -> Response:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["type", "id", "reference", "amount_minor", "currency", "status", "created_at"])
    for payment_item in db.scalars(
        select(Payment)
        .where(
            or_(
                Payment.organization_id == principal.organization_id,
                Payment.merchant_organization_id == principal.organization_id,
            )
        )
        .order_by(Payment.created_at.desc())
    ):
        writer.writerow(
            ["payment", payment_item.id, payment_item.reference, payment_item.amount, payment_item.currency, payment_item.status.value, payment_item.created_at]
        )
    for transfer_item in db.scalars(
        select(Transfer)
        .where(Transfer.organization_id == principal.organization_id)
        .order_by(Transfer.created_at.desc())
    ):
        writer.writerow(
            ["transfer", transfer_item.id, transfer_item.reference, transfer_item.amount, transfer_item.currency, transfer_item.status.value, transfer_item.created_at]
        )
    headers = {"Content-Disposition": 'attachment; filename="fincore-transactions.csv"'}
    return Response(output.getvalue(), media_type="text/csv", headers=headers)


@router.post("/provider-webhooks/{provider_name}")
async def provider_webhook(
    provider_name: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    signature: Annotated[str, Header(alias="X-Provider-Signature")],
) -> dict[str, str]:
    provider = get_provider()
    if provider.name != provider_name:
        raise NotFound("Provider")
    payload = await request.body()
    try:
        event = provider.verify_webhook(payload, signature)
    except ValueError as exc:
        raise DomainError("PROVIDER_SIGNATURE_INVALID", "Provider signature is invalid.", 401) from exc
    external_event_id = str(event.get("id", ""))
    event_type = str(event.get("event_type", ""))
    resource_id = str(event.get("resource_id", ""))
    if not external_event_id or not event_type or not resource_id:
        raise DomainError("PROVIDER_EVENT_INVALID", "Provider event is missing required fields.", 400)
    payload_hash = hashlib.sha256(payload).hexdigest()
    existing = db.scalar(
        select(ProviderEvent).where(
            ProviderEvent.provider == provider_name,
            ProviderEvent.external_event_id == external_event_id,
        )
    )
    if existing is not None:
        if existing.payload_hash != payload_hash:
            raise DomainError("PROVIDER_REPLAY_CONFLICT", "Provider event ID was reused.", 409)
        return {"status": "already_processed", "event_id": existing.id}
    stored = ProviderEvent(
        provider=provider_name,
        external_event_id=external_event_id,
        event_type=event_type,
        payload_hash=payload_hash,
    )
    db.add(stored)
    db.flush()
    if event_type == "deposit.completed":
        complete_deposit(
            db,
            deposit_id=resource_id,
            actor_id=None,
            authorized_development_confirmation=provider_name == "development",
        )
    elif event_type == "withdrawal.completed":
        complete_withdrawal(
            db,
            withdrawal_id=resource_id,
            actor_id=None,
            authorized_development_confirmation=provider_name == "development",
        )
    else:
        raise DomainError("PROVIDER_EVENT_UNSUPPORTED", "Provider event type is unsupported.", 400)
    stored.processed_at = datetime.now(UTC)
    db.commit()
    return {"status": "processed", "event_id": stored.id}
