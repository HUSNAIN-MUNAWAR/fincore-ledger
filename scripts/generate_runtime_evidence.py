"""Run the public-dataset ledger seed and render measured accounting evidence."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def render_journal_video(
    journals: list[dict], output: Path
) -> tuple[int, int, float, int]:
    width, height, fps = 1280, 720, 2.0
    writer = cv2.VideoWriter(
        str(output), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height)
    )
    if not writer.isOpened():
        raise RuntimeError(f"Could not open video writer for {output}")
    for index, journal in enumerate(journals, start=1):
        frame = np.full((height, width, 3), (18, 24, 38), dtype=np.uint8)
        balanced = journal["debits"] == journal["credits"]
        color = (70, 210, 125) if balanced else (60, 80, 235)
        cv2.putText(
            frame,
            "FINCORE LEDGER | DOUBLE-ENTRY VERIFICATION",
            (52, 70),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.96,
            (230, 236, 248),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            f"journal {index} / {len(journals)}",
            (53, 112),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.72,
            (150, 170, 198),
            2,
            cv2.LINE_AA,
        )
        cv2.rectangle(frame, (52, 165), (1228, 330), (35, 46, 68), -1)
        cv2.putText(
            frame,
            f"reference: {journal['reference']}",
            (80, 215),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.82,
            (240, 244, 250),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            f"source: {journal['source_type']}  |  currency: {journal['currency']}",
            (80, 270),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.70,
            (180, 190, 205),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            f"kind: {journal['entry_kind']}  |  status: {journal['status']}",
            (80, 315),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.70,
            (180, 190, 205),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            f"debits: {journal['debits']:,} minor units",
            (90, 430),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.86,
            (130, 190, 245),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            f"credits: {journal['credits']:,} minor units",
            (690, 430),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.86,
            (130, 190, 245),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            "BALANCED" if balanced else "UNBALANCED",
            (90, 570),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.16,
            color,
            3,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            f"postings: {journal['posting_count']}  |  journal id: {journal['id'][:12]}",
            (90, 630),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.68,
            (190, 200, 215),
            2,
            cv2.LINE_AA,
        )
        writer.write(frame)
    writer.release()
    return width, height, fps, len(journals)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir", type=Path, default=ROOT / "docs/runtime_evidence"
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="fincore-runtime-") as temp_dir:
        os.environ["FINCORE_ENV"] = "development"
        os.environ["FINCORE_DATABASE_URL"] = (
            f"sqlite:///{Path(temp_dir) / 'fincore-runtime.sqlite3'}"
        )
        os.environ["FINCORE_PROVIDER_MODE"] = "development"
        from fincore.db.base import Base
        from fincore.db.models import (
            JournalEntry,
            LedgerPosting,
            ReconciliationRun,
            Wallet,
        )
        from fincore.db.session import SessionLocal, engine
        from fincore.public_dataset_seed import DEFAULT_SAMPLE_PATH, seed_public_dataset

        Base.metadata.create_all(engine)
        with SessionLocal() as db:
            first = seed_public_dataset(db)
            second = seed_public_dataset(db)
            journal_rows = (
                db.query(JournalEntry)
                .order_by(JournalEntry.created_at, JournalEntry.id)
                .all()
            )
            wallets = db.query(Wallet).order_by(Wallet.created_at, Wallet.id).all()
            reconciliation = (
                db.query(ReconciliationRun)
                .order_by(ReconciliationRun.started_at.desc())
                .first()
            )
            journals = []
            for journal in journal_rows:
                postings = (
                    db.query(LedgerPosting)
                    .filter(LedgerPosting.journal_entry_id == journal.id)
                    .all()
                )
                debits = sum(
                    item.amount for item in postings if item.direction.value == "debit"
                )
                credits = sum(
                    item.amount for item in postings if item.direction.value == "credit"
                )
                journals.append(
                    {
                        "id": journal.id,
                        "reference": journal.reference,
                        "source_type": journal.source_type,
                        "currency": journal.currency,
                        "entry_kind": journal.entry_kind,
                        "status": journal.status.value,
                        "debits": debits,
                        "credits": credits,
                        "posting_count": len(postings),
                        "balanced": debits == credits,
                    }
                )
            wallet_rows = [
                {
                    "id": wallet.id,
                    "currency": wallet.currency,
                    "ledger_balance": wallet.ledger_balance,
                    "available_balance": wallet.available_balance,
                    "reserved_balance": wallet.reserved_balance,
                }
                for wallet in wallets
            ]
            summary = {
                "status": "completed",
                "dataset": str(DEFAULT_SAMPLE_PATH.relative_to(ROOT)),
                "dataset_sha256": sha256(DEFAULT_SAMPLE_PATH),
                "first_seed": {
                    "payments_created": first.payments_created,
                    "refunds_created": first.refunds_created,
                    "withdrawals_created": first.withdrawals_created,
                    "reconciliation_matched": first.reconciliation_matched,
                    "reconciliation_mismatches": first.reconciliation_mismatches,
                    "total_payment_minor_units": first.total_payment_minor_units,
                },
                "second_seed_idempotent": {
                    "payments_created": second.payments_created,
                    "refunds_created": second.refunds_created,
                    "withdrawals_created": second.withdrawals_created,
                    "reconciliation_matched": second.reconciliation_matched,
                    "reconciliation_mismatches": second.reconciliation_mismatches,
                },
                "journal_count": len(journals),
                "balanced_journals": sum(item["balanced"] for item in journals),
                "wallet_count": len(wallet_rows),
                "wallets": wallet_rows,
                "latest_reconciliation": {
                    "status": reconciliation.status.value if reconciliation else None,
                    "matched_count": reconciliation.matched_count
                    if reconciliation
                    else None,
                    "mismatch_count": reconciliation.mismatch_count
                    if reconciliation
                    else None,
                },
                "claim_boundary": "This is a local SQLite development run over the committed UCI Online Retail sample; it does not claim regulated payment processing, production PostgreSQL concurrency, or a real provider settlement.",
            }

        engine.dispose()
        trace_json = args.output_dir / "ledger-runtime-trace.json"
        trace_json.write_text(
            json.dumps({"summary": summary, "journals": journals}, indent=2) + "\n",
            encoding="utf-8",
        )
        trace_csv = args.output_dir / "ledger-runtime-trace.csv"
        with trace_csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(journals[0]))
            writer.writeheader()
            writer.writerows(journals)
        video = args.output_dir / "ledger-runtime-trace.mp4"
        width, height, fps, frames = render_journal_video(journals, video)
        capture = cv2.VideoCapture(str(video))
        decoded_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        ok, poster = capture.read()
        capture.release()
        if not ok:
            raise RuntimeError("Could not decode the first evidence frame")
        poster_path = args.output_dir / "ledger-runtime-trace-poster.jpg"
        cv2.imwrite(str(poster_path), poster)

    summary["video"] = {
        "width": width,
        "height": height,
        "fps": fps,
        "rendered_frames": frames,
        "decoded_frames": decoded_frames,
    }
    summary["artifacts"] = {
        path.name: {"bytes": path.stat().st_size, "sha256": sha256(path)}
        for path in (trace_json, trace_csv, video, poster_path)
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
