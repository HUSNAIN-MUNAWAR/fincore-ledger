from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from fincore.api.deps import Principal, require_permission
from fincore.core.errors import NotFound
from fincore.db.models import (
    ComplianceReview,
    FeeRule,
    LedgerAccount,
    Membership,
    Organization,
    PostingDirection,
    TransactionLimit,
    User,
    VerificationStatus,
)
from fincore.db.session import get_db
from fincore.services.audit import record_audit
from fincore.services.ledger import PostingSpec, post_journal

router = APIRouter(prefix="/admin", tags=["Administration"])


class FeeRuleCreate(BaseModel):
    organization_id: str | None = None
    operation_type: str = Field(min_length=2, max_length=40)
    currency: str = Field(min_length=3, max_length=3)
    fixed_amount: int = Field(default=0, ge=0)
    percentage_bps: int = Field(default=0, ge=0, le=10_000)
    minimum_fee: int = Field(default=0, ge=0)
    maximum_fee: int | None = Field(default=None, ge=0)


class LimitUpsert(BaseModel):
    organization_id: str
    operation_type: str = Field(min_length=2, max_length=40)
    currency: str = Field(min_length=3, max_length=3)
    minimum_amount: int = Field(default=1, ge=1)
    maximum_amount: int = Field(gt=0)
    daily_amount: int = Field(gt=0)
    monthly_amount: int = Field(gt=0)


class AdjustmentCreate(BaseModel):
    debit_account_id: str
    credit_account_id: str
    amount: int = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    reference: str = Field(min_length=3, max_length=120)
    reason: str = Field(min_length=10, max_length=500)


class ComplianceCreate(BaseModel):
    organization_id: str
    resource_type: str = Field(min_length=2, max_length=40)
    resource_id: str
    risk_flags: list[str] = Field(default_factory=list)
    notes: str = Field(default="", max_length=2000)


class ComplianceDecision(BaseModel):
    status: VerificationStatus
    notes: str = Field(min_length=3, max_length=2000)


@router.get("/organizations")
def list_organizations(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("users.manage"))],
) -> list[dict[str, Any]]:
    organizations = db.scalars(select(Organization).order_by(Organization.created_at.desc())).all()
    return [
        {
            "id": item.id,
            "name": item.name,
            "type": item.type.value,
            "status": item.status.value,
            "default_currency": item.default_currency,
            "verification_status": item.verification_status.value,
            "risk_level": item.risk_level,
            "created_at": item.created_at,
        }
        for item in organizations
    ]


@router.get("/users")
def list_users(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("users.manage"))],
) -> list[dict[str, Any]]:
    rows = db.execute(
        select(User, Membership, Organization)
        .join(Membership, Membership.user_id == User.id)
        .join(Organization, Organization.id == Membership.organization_id)
        .order_by(User.created_at.desc())
    ).all()
    return [
        {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "status": user.status,
            "organization_id": organization.id,
            "organization_name": organization.name,
            "membership_status": membership.status,
        }
        for user, membership, organization in rows
    ]


@router.get("/fee-rules")
def list_fee_rules(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("fees.manage"))],
) -> list[dict[str, Any]]:
    rules = db.scalars(select(FeeRule).order_by(FeeRule.created_at.desc())).all()
    return [
        {
            "id": item.id,
            "organization_id": item.organization_id,
            "operation_type": item.operation_type,
            "currency": item.currency,
            "fixed_amount": item.fixed_amount,
            "percentage_bps": item.percentage_bps,
            "minimum_fee": item.minimum_fee,
            "maximum_fee": item.maximum_fee,
            "active": item.active,
        }
        for item in rules
    ]


@router.post("/fee-rules", status_code=201)
def create_fee_rule(
    payload: FeeRuleCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("fees.manage"))],
) -> dict[str, Any]:
    item = FeeRule(**payload.model_dump())
    db.add(item)
    db.flush()
    record_audit(
        db,
        actor_id=principal.user_id,
        organization_id=principal.organization_id,
        action="fee_rule.created",
        resource_type="fee_rule",
        resource_id=item.id,
        new_values=payload.model_dump(mode="json"),
    )
    db.commit()
    return {"id": item.id, **payload.model_dump(mode="json"), "active": item.active}


@router.put("/limits")
def upsert_limit(
    payload: LimitUpsert,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("limits.manage"))],
) -> dict[str, Any]:
    if payload.minimum_amount > payload.maximum_amount:
        raise ValueError("Minimum amount cannot exceed maximum amount")
    item = db.scalar(
        select(TransactionLimit).where(
            TransactionLimit.organization_id == payload.organization_id,
            TransactionLimit.operation_type == payload.operation_type,
            TransactionLimit.currency == payload.currency,
        )
    )
    previous = None
    if item is None:
        item = TransactionLimit(**payload.model_dump())
        db.add(item)
    else:
        previous = {
            "minimum_amount": item.minimum_amount,
            "maximum_amount": item.maximum_amount,
            "daily_amount": item.daily_amount,
            "monthly_amount": item.monthly_amount,
        }
        for key, value in payload.model_dump().items():
            setattr(item, key, value)
    db.flush()
    record_audit(
        db,
        actor_id=principal.user_id,
        organization_id=principal.organization_id,
        action="transaction_limit.updated",
        resource_type="transaction_limit",
        resource_id=item.id,
        previous_values=previous,
        new_values=payload.model_dump(mode="json"),
    )
    db.commit()
    return {"id": item.id, **payload.model_dump(mode="json")}


@router.post("/adjustments", status_code=201)
def create_adjustment(
    payload: AdjustmentCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("adjustments.create"))],
) -> dict[str, Any]:
    if payload.debit_account_id == payload.credit_account_id:
        raise ValueError("Debit and credit accounts must differ")
    accounts = db.scalars(
        select(LedgerAccount)
        .where(LedgerAccount.id.in_([payload.debit_account_id, payload.credit_account_id]))
        .with_for_update()
    ).all()
    if len(accounts) != 2:
        raise NotFound("Ledger account")
    if any(account.currency != payload.currency for account in accounts):
        raise ValueError("Adjustment account currency mismatch")
    entry = post_journal(
        db,
        organization_id=principal.organization_id,
        reference=payload.reference,
        description=f"Administrative adjustment: {payload.reason}",
        currency=payload.currency,
        source_type="administrative_adjustment",
        source_id=str(uuid.uuid4()),
        postings=[
            PostingSpec(
                payload.debit_account_id,
                PostingDirection.DEBIT,
                payload.amount,
                payload.reason,
            ),
            PostingSpec(
                payload.credit_account_id,
                PostingDirection.CREDIT,
                payload.amount,
                payload.reason,
            ),
        ],
        entry_kind="adjustment",
    )
    record_audit(
        db,
        actor_id=principal.user_id,
        organization_id=principal.organization_id,
        action="ledger.adjustment_posted",
        resource_type="journal_entry",
        resource_id=entry.id,
        new_values={
            "debit_account_id": payload.debit_account_id,
            "credit_account_id": payload.credit_account_id,
            "amount": payload.amount,
            "currency": payload.currency,
        },
        justification=payload.reason,
    )
    db.commit()
    return {"journal_entry_id": entry.id, "reference": entry.reference, "status": entry.status.value}


@router.get("/compliance-reviews")
def list_compliance_reviews(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("compliance.review"))],
) -> list[dict[str, Any]]:
    reviews = db.scalars(
        select(ComplianceReview).order_by(ComplianceReview.created_at.desc()).limit(200)
    ).all()
    return [
        {
            "id": item.id,
            "organization_id": item.organization_id,
            "resource_type": item.resource_type,
            "resource_id": item.resource_id,
            "status": item.status.value,
            "risk_flags": item.risk_flags,
            "notes": item.notes,
            "assigned_to": item.assigned_to,
            "decided_by": item.decided_by,
            "created_at": item.created_at,
        }
        for item in reviews
    ]


@router.post("/compliance-reviews", status_code=201)
def create_compliance_review(
    payload: ComplianceCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("compliance.review"))],
) -> dict[str, Any]:
    item = ComplianceReview(
        **payload.model_dump(),
        status=VerificationStatus.PENDING,
        assigned_to=principal.user_id,
    )
    db.add(item)
    db.flush()
    record_audit(
        db,
        actor_id=principal.user_id,
        organization_id=principal.organization_id,
        action="compliance_review.created",
        resource_type="compliance_review",
        resource_id=item.id,
        new_values=payload.model_dump(mode="json"),
    )
    db.commit()
    return {"id": item.id, "status": item.status.value}


@router.post("/compliance-reviews/{review_id}/decision")
def decide_compliance_review(
    review_id: str,
    payload: ComplianceDecision,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("compliance.review"))],
) -> dict[str, Any]:
    item = db.scalar(
        select(ComplianceReview).where(ComplianceReview.id == review_id).with_for_update()
    )
    if item is None:
        raise NotFound("Compliance review")
    previous = item.status.value
    item.status = payload.status
    item.notes = payload.notes
    item.decided_by = principal.user_id
    item.updated_at = datetime.now(UTC)
    record_audit(
        db,
        actor_id=principal.user_id,
        organization_id=principal.organization_id,
        action="compliance_review.decided",
        resource_type="compliance_review",
        resource_id=item.id,
        previous_values={"status": previous},
        new_values={"status": item.status.value, "notes": payload.notes},
        justification=payload.notes,
    )
    db.commit()
    return {"id": item.id, "status": item.status.value}
