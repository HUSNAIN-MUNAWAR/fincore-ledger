from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fincore.core.errors import IdempotencyConflict
from fincore.db.models import IdempotencyRecord


def request_fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def execute_idempotent[T](
    db: Session,
    *,
    organization_id: str,
    user_id: str,
    key: str,
    path: str,
    payload: dict[str, Any],
    operation: Callable[[], tuple[T, dict[str, Any], int]],
) -> tuple[T | None, dict[str, Any], int, bool]:
    fingerprint = request_fingerprint(payload)
    existing = db.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.organization_id == organization_id,
            IdempotencyRecord.key == key,
        )
    )
    if existing:
        if existing.request_hash != fingerprint or existing.request_path != path:
            raise IdempotencyConflict()
        if not existing.completed or existing.response_body is None or existing.response_status is None:
            raise IdempotencyConflict()
        return None, existing.response_body, existing.response_status, True

    record = IdempotencyRecord(
        organization_id=organization_id,
        user_id=user_id,
        key=key,
        request_path=path,
        request_hash=fingerprint,
        expires_at=datetime.now(UTC) + timedelta(hours=24),
    )
    db.add(record)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        winner = db.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.organization_id == organization_id,
                IdempotencyRecord.key == key,
            )
        )
        if winner is None or winner.request_hash != fingerprint or not winner.completed:
            raise IdempotencyConflict() from None
        return None, winner.response_body or {}, winner.response_status or 200, True

    result, response, status = operation()
    record.response_body = response
    record.response_status = status
    record.completed = True
    db.commit()
    return result, response, status, False
