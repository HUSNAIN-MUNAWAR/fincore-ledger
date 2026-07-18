from __future__ import annotations

from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from fincore.api.deps import Principal, require_permission
from fincore.api.schemas import (
    DepositCreate,
    DepositView,
    PaymentCreate,
    PaymentView,
    RefundCreate,
    RefundView,
    TransferCreate,
    TransferView,
    WithdrawalCreate,
    WithdrawalView,
)
from fincore.core.errors import NotFound
from fincore.db.models import Deposit, Payment, Refund, Transfer, Withdrawal
from fincore.db.session import get_db
from fincore.services.financial import (
    capture_payment,
    create_deposit,
    create_payment,
    create_refund,
    create_transfer,
    request_withdrawal,
)
from fincore.services.idempotency import execute_idempotent

router = APIRouter(tags=["Financial transactions"])


def _json(model: Any, schema: type[Any]) -> dict[str, Any]:
    return cast(dict[str, Any], schema.model_validate(model).model_dump(mode="json"))


@router.post("/transfers", response_model=TransferView, status_code=201)
def transfer(
    payload: TransferCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("transfers.create"))],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
) -> dict[str, Any]:
    def operation() -> tuple[Transfer, dict[str, Any], int]:
        item = create_transfer(
            db,
            organization_id=principal.organization_id,
            actor_id=principal.user_id,
            **payload.model_dump(),
            correlation_id=getattr(request.state, "correlation_id", None),
        )
        return item, _json(item, TransferView), 201

    _, response, _, _ = execute_idempotent(
        db,
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        key=idempotency_key,
        path=str(request.url.path),
        payload=payload.model_dump(mode="json"),
        operation=operation,
    )
    return response


@router.get("/transfers", response_model=list[TransferView])
def list_transfers(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("wallets.read"))],
) -> list[Transfer]:
    return list(
        db.scalars(
            select(Transfer)
            .where(Transfer.organization_id == principal.organization_id)
            .order_by(Transfer.created_at.desc())
            .limit(100)
        ).all()
    )


@router.post("/payments", response_model=PaymentView, status_code=201)
def payment(
    payload: PaymentCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("payments.create"))],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
) -> dict[str, Any]:
    def operation() -> tuple[Payment, dict[str, Any], int]:
        values = payload.model_dump()
        values["metadata"] = values.pop("metadata")
        item = create_payment(
            db,
            organization_id=principal.organization_id,
            actor_id=principal.user_id,
            **values,
            correlation_id=getattr(request.state, "correlation_id", None),
        )
        return item, _json(item, PaymentView), 201

    _, response, _, _ = execute_idempotent(
        db,
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        key=idempotency_key,
        path=str(request.url.path),
        payload=payload.model_dump(mode="json"),
        operation=operation,
    )
    return response


@router.get("/payments", response_model=list[PaymentView])
def list_payments(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("payments.read"))],
) -> list[Payment]:
    return list(
        db.scalars(
            select(Payment)
            .where(
                or_(
                    Payment.organization_id == principal.organization_id,
                    Payment.merchant_organization_id == principal.organization_id,
                )
            )
            .order_by(Payment.created_at.desc())
            .limit(100)
        ).all()
    )


@router.get("/payments/{payment_id}", response_model=PaymentView)
def get_payment(
    payment_id: str,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("payments.read"))],
) -> Payment:
    item = db.scalar(
        select(Payment).where(
            Payment.id == payment_id,
            or_(
                Payment.organization_id == principal.organization_id,
                Payment.merchant_organization_id == principal.organization_id,
            ),
        )
    )
    if item is None:
        raise NotFound("Payment")
    return item


@router.post("/payments/{payment_id}/capture", response_model=PaymentView)
def capture(
    payment_id: str,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("payments.create"))],
) -> Payment:
    item = capture_payment(
        db,
        payment_id=payment_id,
        actor_id=principal.user_id,
        organization_id=principal.organization_id,
    )
    db.commit()
    return item


@router.post("/payments/{payment_id}/refunds", response_model=RefundView, status_code=201)
def refund(
    payment_id: str,
    payload: RefundCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("payments.refund"))],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
) -> dict[str, Any]:
    payment_item = db.get(Payment, payment_id)
    if payment_item is None or payment_item.merchant_organization_id != principal.organization_id:
        raise NotFound("Payment")

    def operation() -> tuple[Refund, dict[str, Any], int]:
        item = create_refund(
            db,
            organization_id=principal.organization_id,
            actor_id=principal.user_id,
            payment_id=payment_id,
            amount=payload.amount,
            reason=payload.reason,
            correlation_id=getattr(request.state, "correlation_id", None),
        )
        return item, _json(item, RefundView), 201

    request_payload = payload.model_dump(mode="json") | {"payment_id": payment_id}
    _, response, _, _ = execute_idempotent(
        db,
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        key=idempotency_key,
        path=str(request.url.path),
        payload=request_payload,
        operation=operation,
    )
    return response


@router.get("/refunds", response_model=list[RefundView])
def list_refunds(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("payments.read"))],
) -> list[Refund]:
    return list(
        db.scalars(
            select(Refund)
            .join(Payment, Payment.id == Refund.payment_id)
            .where(
                or_(
                    Payment.organization_id == principal.organization_id,
                    Payment.merchant_organization_id == principal.organization_id,
                )
            )
            .order_by(Refund.created_at.desc())
            .limit(100)
        ).all()
    )


@router.post("/deposits", response_model=DepositView, status_code=201)
def deposit(
    payload: DepositCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("deposits.create"))],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
) -> dict[str, Any]:
    def operation() -> tuple[Deposit, dict[str, Any], int]:
        item = create_deposit(
            db,
            organization_id=principal.organization_id,
            actor_id=principal.user_id,
            **payload.model_dump(),
        )
        return item, _json(item, DepositView), 201

    _, response, _, _ = execute_idempotent(
        db,
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        key=idempotency_key,
        path=str(request.url.path),
        payload=payload.model_dump(mode="json"),
        operation=operation,
    )
    return response


@router.get("/deposits", response_model=list[DepositView])
def list_deposits(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("wallets.read"))],
) -> list[Deposit]:
    return list(
        db.scalars(
            select(Deposit)
            .where(Deposit.organization_id == principal.organization_id)
            .order_by(Deposit.created_at.desc())
            .limit(100)
        ).all()
    )


@router.post("/withdrawals", response_model=WithdrawalView, status_code=201)
def withdrawal(
    payload: WithdrawalCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("withdrawals.create"))],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
) -> dict[str, Any]:
    def operation() -> tuple[Withdrawal, dict[str, Any], int]:
        item = request_withdrawal(
            db,
            organization_id=principal.organization_id,
            actor_id=principal.user_id,
            **payload.model_dump(),
        )
        return item, _json(item, WithdrawalView), 201

    _, response, _, _ = execute_idempotent(
        db,
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        key=idempotency_key,
        path=str(request.url.path),
        payload=payload.model_dump(mode="json"),
        operation=operation,
    )
    return response


@router.get("/withdrawals", response_model=list[WithdrawalView])
def list_withdrawals(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("wallets.read"))],
) -> list[Withdrawal]:
    query = select(Withdrawal).order_by(Withdrawal.created_at.desc()).limit(100)
    if "withdrawals.review" not in principal.permissions:
        query = query.where(Withdrawal.organization_id == principal.organization_id)
    return list(db.scalars(query).all())
