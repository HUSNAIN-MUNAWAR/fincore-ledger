import pytest

from fincore.core.errors import InvalidTransition
from fincore.domain.fees import calculate_fee
from fincore.domain.money import Money
from fincore.domain.states import PAYMENT_TRANSITIONS, validate_transition


def test_money_requires_integer_minor_units() -> None:
    assert (Money(1099, "usd") + Money(1, "USD")) == Money(1100, "USD")
    with pytest.raises(TypeError):
        Money(10.5, "USD")  # type: ignore[arg-type]


def test_fee_calculation_snapshots_round_up_and_cap() -> None:
    fee = calculate_fee(10_001, fixed_amount=10, percentage_bps=250, minimum_fee=100, maximum_fee=300)
    assert fee.calculated_fee == 261
    assert fee.as_dict()["percentage_bps"] == 250


def test_state_transition_rejects_arbitrary_mutation() -> None:
    validate_transition(PAYMENT_TRANSITIONS, "created", "captured")
    with pytest.raises(InvalidTransition):
        validate_transition(PAYMENT_TRANSITIONS, "refunded", "captured")


def test_webhook_signature_is_deterministic_and_payload_bound() -> None:
    from fincore.core.security import sign_webhook

    first = sign_webhook("secret", 1_700_000_000, b'{"id":"evt_1"}')
    second = sign_webhook("secret", 1_700_000_000, b'{"id":"evt_1"}')
    changed = sign_webhook("secret", 1_700_000_000, b'{"id":"evt_2"}')
    assert first == second
    assert first != changed
    assert len(first) == 64


def test_role_permission_matrix_separates_customer_and_operations_actions() -> None:
    from fincore.domain.permissions import ROLE_PERMISSIONS

    assert "transfers.create" in ROLE_PERMISSIONS["customer"]
    assert "withdrawals.review" not in ROLE_PERMISSIONS["customer"]
    assert "withdrawals.review" in ROLE_PERMISSIONS["operations_manager"]
    assert "adjustments.create" in ROLE_PERMISSIONS["finance_reviewer"]
