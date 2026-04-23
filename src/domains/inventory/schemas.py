"""
Inventory Domain Schemas
========================
Pydantic schemas for inventory API
"""

from pydantic import BaseModel, Field, ConfigDict
from uuid import UUID
from datetime import datetime
from typing import Optional, List
from decimal import Decimal
from enum import Enum


# ---- Enums ----


class ReservationStatus(str, Enum):
    RESERVED = "reserved"
    RELEASED = "released"
    CONSUMED = "consumed"


# ---- Variant Inventory (read model joining SupplierVariant + ProductVariant) ----


class VariantInventoryResponse(BaseModel):
    """Inventory details for a single variant."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(description="SupplierVariant UUID")
    variant_id: UUID = Field(description="ProductVariant UUID")
    sku: Optional[str] = None
    attributes: dict = Field(default_factory=dict, description="Variant attributes e.g. color/size")
    cost_price: Decimal = Field(description="Supplier cost in Toman")
    inventory: int = Field(description="Total stock held")
    reserved_inventory: int = Field(description="Stock reserved for orders")
    available_inventory: int = Field(description="inventory - reserved_inventory")
    status: str
    updated_at: datetime


class VariantInventoryListResponse(BaseModel):
    """Paginated list of variant inventory."""

    items: List[VariantInventoryResponse]
    total: int


# ---- Inventory Override (PATCH) ----


class InventoryOverrideRequest(BaseModel):
    quantity: int = Field(..., description="New absolute inventory quantity")
    reason: str = Field(..., min_length=1, max_length=500, description="Reason for override")


# ---- Inventory Adjust (POST adjust) ----


class InventoryAdjustRequest(BaseModel):
    quantity_change: int = Field(..., description="Positive to add, negative to subtract")
    reason: str = Field(..., min_length=1, max_length=500, description="Reason for adjustment")


class InventoryLogResponse(BaseModel):
    """Single inventory log entry."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    variant_id: UUID
    old_inventory: int
    new_inventory: int
    change: int
    source: str
    reference_id: Optional[UUID] = None
    reference_type: Optional[str] = None
    reason: Optional[str] = None
    extra_data: Optional[dict] = Field(None, description="Metadata JSONB column")
    created_at: datetime


# ---- Reservation ----


class InventoryReservationResponse(BaseModel):
    """Inventory reservation details."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    variant_id: UUID
    order_item_id: UUID
    quantity: int
    status: str
    expires_at: datetime
    released_at: Optional[datetime] = None
    released_reason: Optional[str] = None
    created_at: datetime
