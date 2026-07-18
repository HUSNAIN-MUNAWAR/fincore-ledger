from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FeeSnapshot:
    fixed_amount: int
    percentage_bps: int
    minimum_fee: int
    maximum_fee: int | None
    calculated_fee: int

    def as_dict(self) -> dict[str, int | None]:
        return {
            "fixed_amount": self.fixed_amount,
            "percentage_bps": self.percentage_bps,
            "minimum_fee": self.minimum_fee,
            "maximum_fee": self.maximum_fee,
            "calculated_fee": self.calculated_fee,
        }


def calculate_fee(
    amount: int,
    *,
    fixed_amount: int = 0,
    percentage_bps: int = 0,
    minimum_fee: int = 0,
    maximum_fee: int | None = None,
) -> FeeSnapshot:
    if amount <= 0:
        raise ValueError("Amount must be positive")
    if min(fixed_amount, percentage_bps, minimum_fee) < 0:
        raise ValueError("Fee components cannot be negative")
    percentage_component = (amount * percentage_bps + 9_999) // 10_000
    fee = max(minimum_fee, fixed_amount + percentage_component)
    if maximum_fee is not None:
        fee = min(fee, maximum_fee)
    return FeeSnapshot(fixed_amount, percentage_bps, minimum_fee, maximum_fee, fee)
