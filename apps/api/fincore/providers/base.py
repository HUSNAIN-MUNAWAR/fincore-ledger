from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ProviderResult:
    reference: str
    status: str
    raw: dict[str, Any]


class PaymentProvider(ABC):
    name: str

    @abstractmethod
    def create_deposit(self, *, amount: int, currency: str, reference: str) -> ProviderResult: ...

    @abstractmethod
    def retrieve_deposit(self, reference: str) -> ProviderResult: ...

    @abstractmethod
    def create_payout(
        self, *, amount: int, currency: str, reference: str, destination: str
    ) -> ProviderResult: ...

    @abstractmethod
    def verify_webhook(self, payload: bytes, signature: str) -> dict[str, Any]: ...

    @abstractmethod
    def refund_payment(self, *, reference: str, amount: int) -> ProviderResult: ...
