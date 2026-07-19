from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from fincore.db.models import (
    JournalEntry,
    Organization,
    Payment,
    ReconciliationRun,
    Refund,
    WebhookEndpoint,
)
from fincore.public_dataset_seed import DEFAULT_SAMPLE_PATH, seed_public_dataset


def test_public_dataset_seed_creates_dataset_backed_workflow(db: Session) -> None:
    summary = seed_public_dataset(db, DEFAULT_SAMPLE_PATH)

    payments = db.scalars(select(Payment).where(Payment.reference.startswith("UCI-"))).all()
    refunds = db.scalars(select(Refund)).all()
    journals = db.scalars(select(JournalEntry).where(JournalEntry.reference.startswith("UCI-"))).all()
    organizations = db.scalars(select(Organization).where(Organization.name.startswith("UCI Online Retail"))).all()
    webhook = db.scalar(select(WebhookEndpoint))
    reconciliation = db.scalar(select(ReconciliationRun).order_by(ReconciliationRun.started_at.desc()))

    assert Path(summary.sample_path).exists()
    assert summary.payments_created == len(payments)
    assert len(payments) >= 10
    assert refunds
    assert journals
    assert len(organizations) == 2
    assert webhook is not None
    assert reconciliation is not None
    assert reconciliation.mismatch_count == 0
    assert payments[0].metadata_json["dataset"] == "uci_online_retail"


def test_public_dataset_seed_is_idempotent(db: Session) -> None:
    first = seed_public_dataset(db, DEFAULT_SAMPLE_PATH)
    second = seed_public_dataset(db, DEFAULT_SAMPLE_PATH)

    assert first.payments_created > 0
    assert second.payments_created == 0
    assert second.refunds_created == 0
    assert second.withdrawals_created == 0
