from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Money:
    amount: int
    currency: str

    def __post_init__(self) -> None:
        if not isinstance(self.amount, int):
            raise TypeError("Money amount must use integer minor units")
        if len(self.currency) != 3 or not self.currency.isalpha():
            raise ValueError("Currency must be a 3-letter code")
        object.__setattr__(self, "currency", self.currency.upper())

    def require_positive(self) -> "Money":
        if self.amount <= 0:
            raise ValueError("Amount must be positive")
        return self

    def __add__(self, other: "Money") -> "Money":
        self._same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._same_currency(other)
        return Money(self.amount - other.amount, self.currency)

    def _same_currency(self, other: "Money") -> None:
        if self.currency != other.currency:
            raise ValueError("Currency mismatch")
