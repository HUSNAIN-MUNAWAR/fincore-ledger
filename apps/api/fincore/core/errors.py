from dataclasses import dataclass


@dataclass(slots=True)
class DomainError(Exception):
    code: str
    message: str
    status_code: int = 400


class InsufficientFunds(DomainError):
    def __init__(self) -> None:
        super().__init__("INSUFFICIENT_FUNDS", "The wallet has insufficient available funds.", 409)


class WalletUnavailable(DomainError):
    def __init__(self, status: str) -> None:
        super().__init__("WALLET_UNAVAILABLE", f"The wallet is {status.lower()}.", 409)


class CurrencyMismatch(DomainError):
    def __init__(self) -> None:
        super().__init__("CURRENCY_MISMATCH", "The transaction currencies do not match.", 409)


class InvalidTransition(DomainError):
    def __init__(self, current: str, target: str) -> None:
        super().__init__("INVALID_STATE_TRANSITION", f"Cannot transition from {current} to {target}.", 409)


class IdempotencyConflict(DomainError):
    def __init__(self) -> None:
        super().__init__("IDEMPOTENCY_CONFLICT", "This key was already used with a different request.", 409)


class RefundExceeded(DomainError):
    def __init__(self) -> None:
        super().__init__("REFUND_AMOUNT_EXCEEDED", "Refund exceeds the remaining captured amount.", 409)


class Forbidden(DomainError):
    def __init__(self) -> None:
        super().__init__("FORBIDDEN", "You do not have permission to perform this action.", 403)


class NotFound(DomainError):
    def __init__(self, resource: str) -> None:
        super().__init__("NOT_FOUND", f"{resource} was not found.", 404)


class ProviderUnavailable(DomainError):
    def __init__(self) -> None:
        super().__init__("PROVIDER_UNAVAILABLE", "The payment provider is unavailable.", 503)


class TransactionLimitExceeded(DomainError):
    def __init__(self, limit_name: str) -> None:
        super().__init__(
            "TRANSACTION_LIMIT_EXCEEDED",
            f"The transaction exceeds the configured {limit_name} limit.",
            409,
        )
