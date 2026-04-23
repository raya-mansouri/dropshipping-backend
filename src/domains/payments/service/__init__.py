"""
Payments Domain Service
=======================
Service layer for payment, escrow, wallet, payout, and dispute management.
"""

from .payment_service import (
    PaymentService,
    DEFAULT_PLATFORM_FEE_PERCENT,
    NORMAL_DISPUTE_WINDOW_HOURS,
    HIGH_VALUE_DISPUTE_WINDOW_DAYS,
    HIGH_VALUE_THRESHOLD,
)

__all__ = [
    "PaymentService",
    "DEFAULT_PLATFORM_FEE_PERCENT",
    "NORMAL_DISPUTE_WINDOW_HOURS",
    "HIGH_VALUE_DISPUTE_WINDOW_DAYS",
    "HIGH_VALUE_THRESHOLD",
]
