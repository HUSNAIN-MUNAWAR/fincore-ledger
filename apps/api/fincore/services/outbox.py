from typing import Any

from sqlalchemy.orm import Session

from fincore.db.models import OutboxEvent


def enqueue_event(
    db: Session,
    *,
    organization_id: str,
    event_type: str,
    resource_type: str,
    resource_id: str,
    data: dict[str, Any],
) -> OutboxEvent:
    event = OutboxEvent(
        organization_id=organization_id,
        event_type=event_type,
        resource_type=resource_type,
        resource_id=resource_id,
        payload={
            "api_version": "2026-07-01",
            "type": event_type,
            "organization_id": organization_id,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "data": data,
        },
        deduplication_key=(
            f"{event_type}:{resource_type}:{resource_id}:"
            f"{data.get('refund_id', data.get('status', 'primary'))}"
        ),
    )
    db.add(event)
    return event
