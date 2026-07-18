from collections.abc import Mapping

from fincore.core.errors import InvalidTransition

PAYMENT_TRANSITIONS: Mapping[str, set[str]] = {
    "created": {"requires_action", "processing", "authorized", "captured", "failed", "cancelled"},
    "requires_action": {"processing", "failed", "cancelled", "expired"},
    "processing": {"authorized", "captured", "failed", "cancelled"},
    "authorized": {"captured", "cancelled", "expired"},
    "captured": {"partially_refunded", "refunded"},
    "partially_refunded": {"partially_refunded", "refunded"},
    "refunded": set(),
    "failed": set(),
    "cancelled": set(),
    "expired": set(),
}

TRANSFER_TRANSITIONS: Mapping[str, set[str]] = {
    "created": {"pending", "completed", "failed", "cancelled"},
    "pending": {"completed", "failed", "cancelled"},
    "completed": {"reversed"},
    "failed": set(),
    "reversed": set(),
    "cancelled": set(),
}

WITHDRAWAL_TRANSITIONS: Mapping[str, set[str]] = {
    "requested": {"under_review", "rejected"},
    "under_review": {"approved", "rejected"},
    "approved": {"processing", "rejected"},
    "processing": {"completed", "failed"},
    "completed": {"reversed"},
    "failed": {"reversed"},
    "rejected": set(),
    "reversed": set(),
}

DEPOSIT_TRANSITIONS: Mapping[str, set[str]] = {
    "initiated": {"pending_provider_confirmation", "failed"},
    "pending_provider_confirmation": {"completed", "failed"},
    "completed": {"reversed"},
    "failed": set(),
    "reversed": set(),
}


def validate_transition(transitions: Mapping[str, set[str]], current: str, target: str) -> None:
    if target not in transitions.get(current, set()):
        raise InvalidTransition(current, target)
