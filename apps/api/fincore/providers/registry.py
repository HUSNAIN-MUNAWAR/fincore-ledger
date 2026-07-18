from fincore.core.config import get_settings
from fincore.providers.base import PaymentProvider
from fincore.providers.development import DevelopmentProvider


def get_provider() -> PaymentProvider:
    mode = get_settings().provider_mode
    if mode == "development":
        return DevelopmentProvider()
    raise RuntimeError(f"Provider mode {mode!r} is not configured")
