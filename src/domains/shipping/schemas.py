"""
Shipping Schemas
================
Pydantic v2 request/response schemas for shipping operations.
"""
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, Field


# ---- Shipping Method Schemas ----

class ShippingMethodResponse(BaseModel):
    """Shipping method from platform catalog."""
    id: UUID
    name: str
    shipping_type: str
    external_shipping_id: Optional[str] = None
    active: bool = True

    model_config = {"from_attributes": True}


class ShippingMethodListResponse(BaseModel):
    """Paginated shipping method list."""
    methods: List[ShippingMethodResponse]
    total: int


# ---- Shipment Schemas ----

class ShipmentCreateRequest(BaseModel):
    """Request to create a shipment."""
    order_id: UUID
    order_item_id: UUID
    shipping_method_id: Optional[UUID] = None
    carrier: Optional[str] = None


class ShipmentResponse(BaseModel):
    """Shipment details."""
    id: UUID
    order_id: UUID
    order_item_id: UUID
    shipping_method_id: Optional[UUID] = None
    tracking_code: Optional[str] = None
    carrier: Optional[str] = None
    status: str
    shipped_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    estimated_delivery: Optional[datetime] = None
    actual_delivery: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ShipmentTrackingUpdate(BaseModel):
    """Tracking update for a shipment."""
    tracking_code: str
    carrier: Optional[str] = None
    status: str = Field(pattern=r"^(label_created|shipped|in_transit|delivered|returned|cancelled)$")


class ShipmentListResponse(BaseModel):
    """Paginated shipment list."""
    shipments: List[ShipmentResponse]
    total: int
