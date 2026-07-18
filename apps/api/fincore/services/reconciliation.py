from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from fincore.db.models import (
    LedgerAccount,
    ReconciliationItem,
    ReconciliationRun,
    ReconciliationStatus,
    Wallet,
)
from fincore.services.ledger import account_balance


def run_wallet_reconciliation(db: Session, organization_id: str | None = None) -> ReconciliationRun:
    run = ReconciliationRun(organization_id=organization_id, status=ReconciliationStatus.RUNNING)
    db.add(run)
    db.flush()
    query = select(Wallet)
    if organization_id:
        query = query.where(Wallet.organization_id == organization_id)
    wallets = db.scalars(query).all()
    matched = 0
    mismatches = 0
    for wallet in wallets:
        account = db.scalar(select(LedgerAccount).where(LedgerAccount.wallet_id == wallet.id))
        actual = account_balance(db, account) if account else 0
        if actual == wallet.ledger_balance and wallet.available_balance + wallet.reserved_balance == actual:
            matched += 1
            continue
        mismatches += 1
        db.add(
            ReconciliationItem(
                run_id=run.id,
                organization_id=wallet.organization_id,
                item_type="wallet_balance_mismatch",
                resource_type="wallet",
                resource_id=wallet.id,
                expected_amount=wallet.ledger_balance,
                actual_amount=actual,
                currency=wallet.currency,
            )
        )
    run.matched_count = matched
    run.mismatch_count = mismatches
    run.status = ReconciliationStatus.COMPLETED
    run.completed_at = datetime.now(UTC)
    db.flush()
    return run
