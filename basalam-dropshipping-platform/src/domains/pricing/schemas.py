"""
Pricing Domain Schemas
======================
Pydantic v2 schemas for pricing request/response DTOs
"""
from pydantic import BaseModel, Field, ConfigDict
from uuid import UUID
from datetime import datetime
from decimal import Decimal
from typing import Optional, List


class PriceCalculateRequest(BaseModel):
    """Request schema for price calculation."""

    supplier_price: Decimal = Field(gt=0)
    margin_percent: Decimal = Field(ge=0)
    category_id: Optional[UUID] = None


class PriceCalculateResponse(BaseModel):
    """Response schema for price calculation."""

    supplier_price: Decimal
    margin_percent: Decimal
    seller_price: Decimal
    profit: Decimal
    category_franchise_percent: Decimal
    meets_franchise_requirement: bool


class PriceValidationRequest(BaseModel):
    """Request schema for price validation."""

    seller_price: Decimal = Field(gt=0)
    supplier_price: Decimal = Field(gt=0)
    category_id: UUID


class PriceValidationResponse(BaseModel):
    """Response schema for price validation."""

    is_valid: bool
    margin_percent: Decimal
    category_franchise_percent: Decimal
    validation_errors: List[str]


class PriceHistoryResponse(BaseModel):
    """Response schema for price history records."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    variant_id: UUID
    listing_id: Optional[UUID]
    old_price: Decimal
    new_price: Decimal
    margin_percent: Optional[Decimal]
    margin_changed: Optional[str]
    change_reason: Optional[str]
    created_at: datetime
