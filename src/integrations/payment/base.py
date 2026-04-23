"""
Payment Provider Base
=====================
Abstract base class for payment gateway adapters.
"""
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Dict, Any


class PaymentProvider(ABC):
    """Abstract interface for payment gateway providers."""

    @abstractmethod
    async def create_payment(
        self,
        amount: Decimal,
        callback_url: str,
        description: str = "",
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Create a payment request with the gateway.

        Returns:
            {"status": bool, "token": str, "url": str} on success.
            {"status": False, "message": str} on failure.
        """
        ...

    @abstractmethod
    async def verify_payment(
        self,
        token: str,
        amount: Decimal,
    ) -> Dict[str, Any]:
        """Verify a payment with the gateway.

        Returns:
            {"status": True, "ref_id": int} on success.
            {"status": False, "message": str, "code": int} on failure.
        """
        ...
