from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from fincore.core.crypto import decrypt_secret
from fincore.core.security import sign_webhook
from fincore.db.models import (
    IdempotencyRecord,
    OutboxEvent,
    WebhookDelivery,
    WebhookEndpoint,
)
from fincore.db.session import SessionLocal
from fincore.services.reconciliation import run_wallet_reconciliation
from fincore.worker.celery_app import celery_app


def _encoded_event(event: OutboxEvent) -> bytes:
    payload = dict(event.payload)
    payload["id"] = event.id
    payload["created_at"] = event.created_at.isoformat()
    return json.dumps(payload, separators=(",", ":"), default=str).encode()


def _attempt_delivery(
    db: Session,
    *,
    endpoint: WebhookEndpoint,
    event: OutboxEvent,
    attempt_number: int,
) -> bool:
    delivery = WebhookDelivery(
        endpoint_id=endpoint.id,
        outbox_event_id=event.id,
        attempt_number=attempt_number,
        status="sending",
    )
    db.add(delivery)
    db.flush()
    encoded = _encoded_event(event)
    timestamp = int(datetime.now(UTC).timestamp())
    signature = sign_webhook(decrypt_secret(endpoint.secret_encrypted), timestamp, encoded)
    try:
        response = httpx.post(
            endpoint.url,
            content=encoded,
            headers={
                "Content-Type": "application/json",
                "FinCore-Signature": f"t={timestamp},v1={signature}",
                "FinCore-Event-ID": event.id,
            },
            timeout=5.0,
        )
        delivery.response_status = response.status_code
        delivery.response_excerpt = response.text[:500]
        if 200 <= response.status_code < 300:
            delivery.status = "delivered"
            delivery.delivered_at = datetime.now(UTC)
            return True
    except httpx.HTTPError as exc:
        delivery.response_excerpt = str(exc)[:500]
    delivery.status = "retrying" if attempt_number < 6 else "dead_letter"
    if delivery.status == "retrying":
        delivery.next_attempt_at = datetime.now(UTC) + timedelta(
            seconds=min(3600, 2**attempt_number * 30)
        )
    return False


@celery_app.task(name="fincore.dispatch_outbox")  # type: ignore[untyped-decorator]
def dispatch_outbox() -> dict[str, int]:
    delivered = 0
    failed = 0
    with SessionLocal() as db:
        now = datetime.now(UTC)
        retry_rows = db.execute(
            select(WebhookDelivery, WebhookEndpoint, OutboxEvent)
            .join(WebhookEndpoint, WebhookEndpoint.id == WebhookDelivery.endpoint_id)
            .join(OutboxEvent, OutboxEvent.id == WebhookDelivery.outbox_event_id)
            .where(
                WebhookDelivery.status == "retrying",
                WebhookDelivery.next_attempt_at <= now,
                WebhookEndpoint.enabled.is_(True),
            )
            .order_by(WebhookDelivery.next_attempt_at)
            .limit(50)
            .with_for_update(skip_locked=True)
        ).all()
        for previous, endpoint, event in retry_rows:
            previous.status = "retried"
            if _attempt_delivery(
                db,
                endpoint=endpoint,
                event=event,
                attempt_number=previous.attempt_number + 1,
            ):
                delivered += 1
            else:
                failed += 1

        events = db.scalars(
            select(OutboxEvent)
            .where(OutboxEvent.published_at.is_(None))
            .order_by(OutboxEvent.created_at)
            .limit(50)
            .with_for_update(skip_locked=True)
        ).all()
        for event in events:
            endpoints = db.scalars(
                select(WebhookEndpoint).where(
                    WebhookEndpoint.organization_id == event.organization_id,
                    WebhookEndpoint.enabled.is_(True),
                )
            ).all()
            applicable = [item for item in endpoints if event.event_type in item.subscribed_events]
            for endpoint in applicable:
                if _attempt_delivery(db, endpoint=endpoint, event=event, attempt_number=1):
                    delivered += 1
                else:
                    failed += 1
            event.published_at = datetime.now(UTC)
        db.commit()
    return {"delivered": delivered, "failed": failed}


@celery_app.task(name="fincore.reconcile_wallets")  # type: ignore[untyped-decorator]
def reconcile_wallets() -> dict[str, int]:
    with SessionLocal() as db:
        run = run_wallet_reconciliation(db)
        db.commit()
        return {"matched": run.matched_count, "mismatches": run.mismatch_count}


@celery_app.task(name="fincore.cleanup_idempotency")  # type: ignore[untyped-decorator]
def cleanup_idempotency() -> dict[str, int]:
    with SessionLocal() as db:
        result = db.execute(
            delete(IdempotencyRecord).where(IdempotencyRecord.expires_at < datetime.now(UTC))
        )
        db.commit()
        return {"deleted": int(result.rowcount or 0)}  # type: ignore[attr-defined]
