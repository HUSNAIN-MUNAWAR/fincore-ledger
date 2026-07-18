from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from fincore.api.deps import Principal, get_principal, membership_permissions
from fincore.api.schemas import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserView,
)
from fincore.core.config import get_settings
from fincore.core.errors import DomainError, Forbidden
from fincore.core.security import (
    hash_password,
    issue_access_token,
    new_refresh_token,
    token_hash,
    verify_password,
)
from fincore.db.models import (
    Membership,
    Organization,
    OrganizationType,
    RefreshSession,
    Role,
    User,
    Wallet,
)
from fincore.db.session import get_db
from fincore.services.audit import record_audit
from fincore.services.bootstrap import ensure_rbac
from fincore.services.ledger import ensure_wallet_account

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _issue_session(
    db: Session,
    *,
    user: User,
    organization_id: str,
    request: Request,
) -> TokenResponse:
    permissions = membership_permissions(db, user.id, organization_id)
    if not permissions:
        raise Forbidden()
    access = issue_access_token(
        user_id=user.id,
        organization_id=organization_id,
        permissions=permissions,
    )
    refresh = new_refresh_token()
    settings = get_settings()
    db.add(
        RefreshSession(
            user_id=user.id,
            organization_id=organization_id,
            token_hash=token_hash(refresh),
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_days),
        )
    )
    record_audit(
        db,
        actor_id=user.id,
        organization_id=organization_id,
        action="auth.login",
        resource_type="session",
        resource_id=None,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        request_id=getattr(request.state, "request_id", None),
    )
    db.commit()
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.access_token_minutes * 60,
        organization_id=organization_id,
        permissions=permissions,
    )


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(payload: RegisterRequest, request: Request, db: Annotated[Session, Depends(get_db)]) -> TokenResponse:
    existing = db.scalar(select(User).where(User.email == payload.email.lower()))
    if existing:
        raise DomainError("EMAIL_EXISTS", "An account with this email already exists.", 409)
    ensure_rbac(db)
    role = db.scalar(select(Role).where(Role.name == "customer"))
    if role is None:
        raise RuntimeError("Customer role not configured")
    organization = Organization(
        name=payload.organization_name,
        type=OrganizationType.CUSTOMER,
        default_currency=payload.currency,
        contact_email=payload.email.lower(),
    )
    user = User(
        email=payload.email.lower(),
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
    )
    db.add_all([organization, user])
    db.flush()
    db.add(Membership(organization_id=organization.id, user_id=user.id, role_id=role.id))
    wallet = Wallet(organization_id=organization.id, currency=payload.currency)
    db.add(wallet)
    db.flush()
    ensure_wallet_account(db, wallet)
    record_audit(
        db,
        actor_id=user.id,
        organization_id=organization.id,
        action="user.registered",
        resource_type="user",
        resource_id=user.id,
        new_values={"email": user.email, "organization_id": organization.id},
    )
    return _issue_session(db, user=user, organization_id=organization.id, request=request)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Annotated[Session, Depends(get_db)]) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == payload.email.lower()).with_for_update())
    now = datetime.now(UTC)
    if user is None or not verify_password(payload.password, user.password_hash):
        if user:
            user.failed_login_count += 1
            if user.failed_login_count >= 5:
                user.locked_until = now + timedelta(minutes=15)
            db.commit()
        raise DomainError("INVALID_CREDENTIALS", "Email or password is invalid.", 401)
    locked_until = user.locked_until
    normalized_lock = None
    if locked_until is not None:
        normalized_lock = locked_until.replace(tzinfo=UTC) if locked_until.tzinfo is None else locked_until
    if normalized_lock is not None and normalized_lock > now:
        raise DomainError("ACCOUNT_LOCKED", "The account is temporarily locked.", 423)
    if user.status != "active":
        raise Forbidden()
    membership_query = select(Membership).where(Membership.user_id == user.id, Membership.status == "active")
    if payload.organization_id:
        membership_query = membership_query.where(Membership.organization_id == payload.organization_id)
    membership = db.scalar(membership_query)
    if membership is None:
        raise Forbidden()
    user.failed_login_count = 0
    user.locked_until = None
    return _issue_session(db, user=user, organization_id=membership.organization_id, request=request)


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, request: Request, db: Annotated[Session, Depends(get_db)]) -> TokenResponse:
    session = db.scalar(
        select(RefreshSession)
        .where(RefreshSession.token_hash == token_hash(payload.refresh_token))
        .with_for_update()
    )
    now = datetime.now(UTC)
    if session is None or session.revoked_at is not None:
        raise Forbidden()
    expires = session.expires_at
    if (expires.replace(tzinfo=UTC) if expires.tzinfo is None else expires) <= now:
        raise Forbidden()
    session.revoked_at = now
    user = db.get(User, session.user_id)
    if user is None:
        raise Forbidden()
    return _issue_session(db, user=user, organization_id=session.organization_id, request=request)


@router.post("/logout", status_code=204)
def logout(
    payload: RefreshRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> None:
    session = db.scalar(select(RefreshSession).where(RefreshSession.token_hash == token_hash(payload.refresh_token)))
    if session and session.user_id == principal.user_id:
        session.revoked_at = datetime.now(UTC)
        db.commit()


@router.get("/me", response_model=UserView)
def me(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> User:
    user = db.get(User, principal.user_id)
    if user is None:
        raise Forbidden()
    return user
