from typing import Any

from sqlalchemy.orm import Session

from fincore.db.models import AuditLog


def record_audit(
    db: Session,
    *,
    actor_id: str | None,
    organization_id: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None,
    previous_values: dict[str, Any] | None = None,
    new_values: dict[str, Any] | None = None,
    justification: str | None = None,
    request_id: str | None = None,
    correlation_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    actor_type: str = "user",
) -> AuditLog:
    audit = AuditLog(
        actor_id=actor_id,
        actor_type=actor_type,
        organization_id=organization_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        previous_values=previous_values,
        new_values=new_values,
        justification=justification,
        request_id=request_id,
        correlation_id=correlation_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(audit)
    return audit
