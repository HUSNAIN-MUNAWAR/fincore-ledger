from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fincore.db.models import (
    AccountCategory,
    JournalEntry,
    JournalStatus,
    LedgerAccount,
    LedgerPosting,
    PostingDirection,
    Wallet,
)


@dataclass(frozen=True, slots=True)
class PostingSpec:
    account_id: str
    direction: PostingDirection
    amount: int
    memo: str = ""


def ensure_wallet_account(db: Session, wallet: Wallet) -> LedgerAccount:
    account = db.scalar(select(LedgerAccount).where(LedgerAccount.wallet_id == wallet.id))
    if account:
        return account
    account = LedgerAccount(
        organization_id=wallet.organization_id,
        code=f"WALLET-{wallet.id[:8]}",
        name=f"Wallet liability {wallet.id[:8]}",
        category=AccountCategory.LIABILITY,
        currency=wallet.currency,
        normal_balance=PostingDirection.CREDIT,
        wallet_id=wallet.id,
    )
    db.add(account)
    db.flush()
    return account


def ensure_system_account(
    db: Session,
    *,
    organization_id: str,
    code: str,
    name: str,
    category: AccountCategory,
    currency: str,
    normal_balance: PostingDirection,
) -> LedgerAccount:
    account = db.scalar(
        select(LedgerAccount).where(
            LedgerAccount.organization_id == organization_id,
            LedgerAccount.code == code,
            LedgerAccount.currency == currency,
        )
    )
    if account:
        return account
    account = LedgerAccount(
        organization_id=organization_id,
        code=code,
        name=name,
        category=category,
        currency=currency,
        normal_balance=normal_balance,
        is_system=True,
    )
    db.add(account)
    db.flush()
    return account


def post_journal(
    db: Session,
    *,
    organization_id: str,
    reference: str,
    description: str,
    currency: str,
    source_type: str,
    source_id: str,
    postings: Iterable[PostingSpec],
    correlation_id: str | None = None,
    entry_kind: str = "primary",
    reversal_of_id: str | None = None,
    adjust_available: bool = True,
) -> JournalEntry:
    specs = list(postings)
    if len(specs) < 2:
        raise ValueError("A journal entry requires at least two postings")
    if any(item.amount <= 0 for item in specs):
        raise ValueError("Posting amounts must be positive")
    debits = sum(item.amount for item in specs if item.direction == PostingDirection.DEBIT)
    credits = sum(item.amount for item in specs if item.direction == PostingDirection.CREDIT)
    if debits != credits:
        raise ValueError(f"Unbalanced journal entry: debits={debits} credits={credits}")

    account_ids = {item.account_id for item in specs}
    accounts = {
        account.id: account
        for account in db.scalars(select(LedgerAccount).where(LedgerAccount.id.in_(account_ids))).all()
    }
    if set(accounts) != account_ids:
        raise ValueError("Unknown ledger account")
    if any(account.currency != currency for account in accounts.values()):
        raise ValueError("All postings must use the journal currency")

    entry = JournalEntry(
        organization_id=organization_id,
        reference=reference,
        description=description,
        currency=currency,
        source_type=source_type,
        source_id=source_id,
        entry_kind=entry_kind,
        correlation_id=correlation_id,
        reversal_of_id=reversal_of_id,
    )
    db.add(entry)
    db.flush()
    for spec in specs:
        db.add(
            LedgerPosting(
                journal_entry_id=entry.id,
                account_id=spec.account_id,
                direction=spec.direction,
                amount=spec.amount,
                memo=spec.memo,
            )
        )
        account = accounts[spec.account_id]
        if account.wallet_id:
            wallet = db.get(Wallet, account.wallet_id)
            if wallet is None:
                raise ValueError("Wallet account has no wallet")
            delta = spec.amount if spec.direction == account.normal_balance else -spec.amount
            wallet.ledger_balance += delta
            if adjust_available:
                wallet.available_balance += delta
            wallet.version += 1
            if wallet.ledger_balance < 0 or wallet.available_balance < 0:
                raise ValueError("Posting would create a negative wallet balance")
    db.flush()
    return entry


def reverse_journal(
    db: Session,
    *,
    entry: JournalEntry,
    actor_organization_id: str,
    source_type: str,
    source_id: str,
    reason: str,
    correlation_id: str | None = None,
) -> JournalEntry:
    reverse_specs = [
        PostingSpec(
            account_id=posting.account_id,
            direction=(
                PostingDirection.CREDIT
                if posting.direction == PostingDirection.DEBIT
                else PostingDirection.DEBIT
            ),
            amount=posting.amount,
            memo=f"Reversal: {reason}",
        )
        for posting in entry.postings
    ]
    reversal = post_journal(
        db,
        organization_id=actor_organization_id,
        reference=f"REV-{entry.reference}",
        description=f"Reversal of {entry.reference}: {reason}",
        currency=entry.currency,
        source_type=source_type,
        source_id=source_id,
        postings=reverse_specs,
        correlation_id=correlation_id,
        entry_kind="reversal",
        reversal_of_id=entry.id,
    )
    entry.status = JournalStatus.REVERSED
    return reversal


def account_balance(db: Session, account: LedgerAccount) -> int:
    debit = db.scalar(
        select(func.coalesce(func.sum(LedgerPosting.amount), 0)).where(
            LedgerPosting.account_id == account.id,
            LedgerPosting.direction == PostingDirection.DEBIT,
        )
    )
    credit = db.scalar(
        select(func.coalesce(func.sum(LedgerPosting.amount), 0)).where(
            LedgerPosting.account_id == account.id,
            LedgerPosting.direction == PostingDirection.CREDIT,
        )
    )
    debit_value = int(debit or 0)
    credit_value = int(credit or 0)
    if account.normal_balance == PostingDirection.DEBIT:
        return debit_value - credit_value
    return credit_value - debit_value


def journal_is_balanced(entry: JournalEntry) -> bool:
    debits = sum(p.amount for p in entry.postings if p.direction == PostingDirection.DEBIT)
    credits = sum(p.amount for p in entry.postings if p.direction == PostingDirection.CREDIT)
    return debits == credits
