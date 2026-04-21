"""
Shipping Domain
===============
Handles shipment creation, tracking, and carrier integration.

Delegates to the existing Shipment model in orders/models.py
and the ShipmentRepository in orders/repository/shipment.py.
"""

from .service.shipping_service import ShippingService
from .repository.shipping_method_repository import ShippingMethodRepository

__all__ = [
    "ShippingService",
    "ShippingMethodRepository",
]
