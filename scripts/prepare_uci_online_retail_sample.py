from __future__ import annotations

import argparse
import csv
import hashlib
import json
import urllib.request
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_PATH = REPO_ROOT / "data" / "raw" / "ibm-online-retail-sample.csv"
DEFAULT_OUTPUT_PATH = REPO_ROOT / "data" / "sample" / "uci_online_retail_payments.json"
SAMPLE_SOURCE_URL = (
    "https://raw.githubusercontent.com/IBM/customer_pos_analytics/master/"
    "data/Online%20Retail%20Sample.csv"
)
OFFICIAL_UCI_URL = "https://archive.ics.uci.edu/dataset/352/online%2Bretail"
CITATION = (
    "Chen, D. (2015). Online Retail [Dataset]. UCI Machine Learning Repository. "
    "https://doi.org/10.24432/C5BW33."
)


def money_to_minor_units(value: Decimal) -> int:
    return int((value * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def download_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "fincore-ledger-dataset-prep/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response:
        data = response.read()
    destination.write_bytes(data)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    required = {
        "InvoiceNo",
        "StockCode",
        "Description",
        "Quantity",
        "InvoiceDate",
        "UnitPrice",
        "CustomerID",
        "Country",
    }
    missing = required - set(rows[0] if rows else [])
    if missing:
        raise ValueError(f"Dataset is missing required columns: {', '.join(sorted(missing))}")
    return rows


def aggregate_invoices(
    rows: list[dict[str, str]], max_sales: int, max_refunds: int, source_file_sha256: str
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["InvoiceNo"]].append(row)

    payments: list[dict[str, Any]] = []
    by_customer: dict[str, list[dict[str, Any]]] = defaultdict(list)
    skipped_rows = 0
    for invoice_no, invoice_rows in grouped.items():
        if invoice_no.startswith("C"):
            continue
        if len(payments) >= max_sales:
            break
        clean_rows: list[dict[str, str]] = []
        for row in invoice_rows:
            try:
                quantity = int(row["Quantity"])
                unit_price = Decimal(row["UnitPrice"])
            except Exception:
                skipped_rows += 1
                continue
            if quantity <= 0 or unit_price <= 0 or not row["CustomerID"]:
                skipped_rows += 1
                continue
            clean_rows.append(row)
        if not clean_rows:
            continue
        total = sum(int(row["Quantity"]) * Decimal(row["UnitPrice"]) for row in clean_rows)
        amount_minor = money_to_minor_units(total)
        record = {
            "payment_reference": f"UCI-{invoice_no}",
            "invoice_no": invoice_no,
            "invoice_date": clean_rows[0]["InvoiceDate"],
            "customer_id": clean_rows[0]["CustomerID"],
            "country": clean_rows[0]["Country"],
            "amount_minor": amount_minor,
            "currency": "GBP",
            "description": f"UCI Online Retail invoice {invoice_no}",
            "line_count": len(clean_rows),
            "item_count": sum(int(row["Quantity"]) for row in clean_rows),
            "sample_line_items": [
                {
                    "stock_code": row["StockCode"],
                    "description": row["Description"].strip(),
                    "quantity": int(row["Quantity"]),
                    "unit_price_gbp": str(Decimal(row["UnitPrice"])),
                }
                for row in clean_rows[:5]
            ],
        }
        payments.append(record)
        by_customer[record["customer_id"]].append(record)

    refunds: list[dict[str, Any]] = []
    for invoice_no, invoice_rows in grouped.items():
        if len(refunds) >= max_refunds:
            break
        if not invoice_no.startswith("C"):
            continue
        customer_id = invoice_rows[0]["CustomerID"]
        candidates = by_customer.get(customer_id, [])
        if not candidates:
            continue
        cancellation_total = Decimal("0")
        for row in invoice_rows:
            try:
                cancellation_total += abs(int(row["Quantity"])) * Decimal(row["UnitPrice"])
            except Exception:
                skipped_rows += 1
        refund_amount = money_to_minor_units(cancellation_total)
        payment = next((item for item in candidates if item["amount_minor"] > refund_amount), None)
        if payment is None or refund_amount <= 0:
            continue
        refunds.append(
            {
                "payment_reference": payment["payment_reference"],
                "cancellation_invoice_no": invoice_no,
                "cancellation_date": invoice_rows[0]["InvoiceDate"],
                "amount_minor": refund_amount,
                "currency": "GBP",
                "reason": f"UCI cancellation invoice {invoice_no}",
            }
        )

    return {
        "dataset": {
            "title": "Online Retail",
            "publisher": "UCI Machine Learning Repository",
            "official_source_url": OFFICIAL_UCI_URL,
            "sample_source_url": SAMPLE_SOURCE_URL,
            "license": "Creative Commons Attribution 4.0 International (CC BY 4.0)",
            "citation": CITATION,
            "prepared_on": "2026-07-19",
            "source_file_sha256": source_file_sha256,
        },
        "selection": {
            "source_rows_read": len(rows),
            "payments_selected": len(payments),
            "refunds_selected": len(refunds),
            "skipped_rows": skipped_rows,
            "rules": [
                "Aggregate positive line items by InvoiceNo into wallet payments.",
                "Keep invoice, country, anonymized customer identifier, totals, and a short item sample.",
                "Represent matching cancellation invoices as refunds when a selected payment exists for the same customer.",
                "Exclude raw descriptions beyond the short item sample and ignore missing CustomerID rows.",
            ],
        },
        "payments": payments,
        "refunds": refunds,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare the FinCore public UCI Online Retail demo subset.")
    parser.add_argument("--raw-path", type=Path, default=DEFAULT_RAW_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--max-sales", type=int, default=18)
    parser.add_argument("--max-refunds", type=int, default=3)
    parser.add_argument("--skip-download", action="store_true")
    args = parser.parse_args()

    if not args.skip_download or not args.raw_path.exists():
        print(f"Downloading public sample CSV from {SAMPLE_SOURCE_URL}")
        download_file(SAMPLE_SOURCE_URL, args.raw_path)
    rows = read_rows(args.raw_path)
    source_file_sha256 = hashlib.sha256(args.raw_path.read_bytes()).hexdigest()
    payload = aggregate_invoices(rows, args.max_sales, args.max_refunds, source_file_sha256)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        "Prepared "
        f"{payload['selection']['payments_selected']} payments and "
        f"{payload['selection']['refunds_selected']} refunds at {args.output}"
    )


if __name__ == "__main__":
    main()
