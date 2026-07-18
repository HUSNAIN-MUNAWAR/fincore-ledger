from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from fincore.core.errors import Forbidden
from fincore.core.security import constant_time_equal, decode_access_token, token_hash
from fincore.db.models import ApiKey, Membership, Permission, RolePermission, User
from fincore.db.session import get_db

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: str
    organization_id: str
    permissions: frozenset[str]
    auth_type: str = "jwt"


def get_principal(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> Principal:
    if x_api_key:
        prefix = x_api_key.split(".", 1)[0]
        api_key = db.scalar(select(ApiKey).where(ApiKey.prefix == prefix, ApiKey.revoked_at.is_(None)))
        if api_key is None or not constant_time_equal(api_key.key_hash, token_hash(x_api_key)):
            raise Forbidden()
        if api_key.expires_at and api_key.expires_at < datetime.now(UTC):
            raise Forbidden()
        api_key.last_used_at = datetime.now(UTC)
        db.commit()
        return Principal(
            user_id=api_key.created_by,
            organization_id=api_key.organization_id,
            permissions=frozenset(api_key.scopes),
            auth_type="api_key",
        )
    if credentials is None:
        raise Forbidden()
    try:
        payload = decode_access_token(credentials.credentials)
    except Exception as exc:
        raise Forbidden() from exc
    user = db.get(User, str(payload["sub"]))
    if user is None or user.status != "active":
        raise Forbidden()
    return Principal(
        user_id=str(payload["sub"]),
        organization_id=str(payload["org"]),
        permissions=frozenset(str(item) for item in payload.get("permissions", [])),
    )


def require_permission(code: str):  # type: ignore[no-untyped-def]
    def dependency(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
        if code not in principal.permissions:
            raise Forbidden()
        return principal

    return dependency


def membership_permissions(db: Session, user_id: str, organization_id: str) -> list[str]:
    rows = db.scalars(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(Membership, Membership.role_id == RolePermission.role_id)
        .where(
            Membership.user_id == user_id,
            Membership.organization_id == organization_id,
            Membership.status == "active",
        )
    ).all()
    return sorted(set(rows))
