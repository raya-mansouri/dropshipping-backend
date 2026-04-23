"""
Payment Provider Factory
========================
Returns the configured payment provider instance.
"""
import structlog

from src.core.config import get_settings
from .base import PaymentProvider

logger = structlog.get_logger(__name__)


class PaymentProviderFactory:
    """Factory for creating payment provider instances."""

    _registry: dict[str, type[PaymentProvider]] = {}

    @classmethod
    def register(cls, name: str, provider_class: type[PaymentProvider]) -> None:
        cls._registry[name] = provider_class

    @classmethod
    def get_provider(cls) -> PaymentProvider:
        """Return the payment provider configured in settings."""
        settings = get_settings()
        gateway_name = settings.payment_gateway

        # Lazy import to avoid circular imports at module level
        if gateway_name == "zarinpal":
            from .zarinpal import ZarinpalProvider
            cls._registry.setdefault("zarinpal", ZarinpalProvider)

        provider_class = cls._registry.get(gateway_name)
        if not provider_class:
            raise ValueError(f"Payment gateway '{gateway_name}' is not supported")

        logger.debug("payment_provider_resolved", gateway=gateway_name)
        return provider_class()
