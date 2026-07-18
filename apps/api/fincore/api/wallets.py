from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from fincore.api.deps import Principal, require_permission
from fincore.api.schemas import WalletView
from fincore.core.errors import NotFound
from fincore.db.models import Wallet, WalletStatus
from fincore.db.session import get_db
from fincore.services.audit import record_audit

router = APIRouter(prefix="/wallets", tags=["Wallets"])


@router.get("", response_model=list[WalletView])
def list_wallets(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("wallets.read"))],
) -> list[Wallet]:
    return list(
        db.scalars(
            select(Wallet)
            .where(Wallet.organization_id == principal.organization_id)
            .order_by(Wallet.created_at)
        ).all()
    )


@router.get("/{wallet_id}", response_model=WalletView)
def get_wallet(
    wallet_id: str,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("wallets.read"))],
) -> Wallet:
    wallet = db.scalar(
        select(Wallet).where(Wallet.id == wallet_id, Wallet.organization_id == principal.organization_id)
    )
    if wallet is None:
        raise NotFound("Wallet")
    return wallet


@router.post("/{wallet_id}/freeze", response_model=WalletView)
def freeze_wallet(
    wallet_id: str,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("wallets.manage"))],
) -> Wallet:
    wallet = db.scalar(select(Wallet).where(Wallet.id == wallet_id).with_for_update())
    if wallet is None:
        raise NotFound("Wallet")
    previous = wallet.status.value
    wallet.status = WalletStatus.FROZEN
    record_audit(
        db,
        actor_id=principal.user_id,
        organization_id=principal.organization_id,
        action="wallet.frozen",
        resource_type="wallet",
        resource_id=wallet.id,
        previous_values={"status": previous},
        new_values={"status": wallet.status.value},
    )
    db.commit()
    return wallet


@router.post("/{wallet_id}/unfreeze", response_model=WalletView)
def unfreeze_wallet(
    wallet_id: str,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_permission("wallets.manage"))],
) -> Wallet:
    wallet = db.scalar(select(Wallet).where(Wallet.id == wallet_id).with_for_update())
    if wallet is None:
        raise NotFound("Wallet")
    previous = wallet.status.value
    wallet.status = WalletStatus.ACTIVE
    record_audit(
        db,
        actor_id=principal.user_id,
        organization_id=principal.organization_id,
        action="wallet.unfrozen",
        resource_type="wallet",
        resource_id=wallet.id,
        previous_values={"status": previous},
        new_values={"status": wallet.status.value},
    )
    db.commit()
    return wallet
