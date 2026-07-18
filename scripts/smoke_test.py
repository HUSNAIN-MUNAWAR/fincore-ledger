"""Run a minimal authenticated smoke test against a live FinCore API."""
from __future__ import annotations

import os
import secrets

import httpx

BASE_URL = os.getenv("FINCORE_API_URL", "http://localhost:8000/api/v1")
TIMEOUT_SECONDS = float(os.getenv("FINCORE_SMOKE_TIMEOUT", "30"))


def main() -> None:
    with httpx.Client(base_url=BASE_URL, timeout=TIMEOUT_SECONDS) as client:
        login = client.post(
            "/auth/login",
            json={"email": "customer@fincore.example", "password": "FinCore-Dev-2026!"},
        )
        login.raise_for_status()
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        wallets = client.get("/wallets", headers=headers)
        wallets.raise_for_status()
        summary = client.get("/dashboard/summary", headers=headers)
        summary.raise_for_status()
        print(
            {
                "request_id": summary.headers.get("x-request-id"),
                "wallets": len(wallets.json()),
                "available_balance": summary.json()["available_balance"],
                "smoke_id": secrets.token_hex(4),
            }
        )


if __name__ == "__main__":
    main()
