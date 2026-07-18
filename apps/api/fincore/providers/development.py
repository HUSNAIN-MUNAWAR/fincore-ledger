from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from typing import Any

from fincore.providers.base import PaymentProvider, ProviderResult


class DevelopmentProvider(PaymentProvider):
    """Deterministic local adapter. It never represents a real financial network."""

    name = "development"

    def __init__(self, webhook_secret: str = "development-provider-webhook") -> None:
        self.webhook_secret = webhook_secret

    def create_deposit(self, *, amount: int, currency: str, reference: str) -> ProviderResult:
        provider_ref = f"dev_dep_{secrets.token_hex(8)}"
        return ProviderResult(provider_ref, "pending", {"test_mode": True, "reference": reference})

    def retrieve_deposit(self, reference: str) -> ProviderResult:
        return ProviderResult(reference, "pending", {"test_mode": True})

    def create_payout(
        self, *, amount: int, currency: str, reference: str, destination: str
    ) -> ProviderResult:
        provider_ref = f"dev_pay_{secrets.token_hex(8)}"
        return ProviderResult(
            provider_ref,
            "processing",
            {"test_mode": True, "destination": destination, "reference": reference},
        )

    def verify_webhook(self, payload: bytes, signature: str) -> dict[str, Any]:
        expected = hmac.new(self.webhook_secret.encode(), payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise ValueError("Invalid provider signature")
        value = json.loads(payload)
        if not isinstance(value, dict):
            raise ValueError("Invalid payload")
        return value

    def refund_payment(self, *, reference: str, amount: int) -> ProviderResult:
        return ProviderResult(
            f"dev_ref_{secrets.token_hex(8)}", "completed", {"test_mode": True, "amount": amount}
        )
