"""
Orders Domain Schemas
======================
Pydantic schemas for orders API
"""
from pydantic import BaseModel, Field, ConfigDict
from uuid import UUID
from datetime import datetime
from typing import Optional, List
from decimal import Decimal
from enum import Enum


class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PAID = "paid"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    DISPUTED = "disputed"
    REFUNDED = "refunded"


class ShipmentStatus(str, Enum):
    PENDING = "pending"
    LABEL_CREATED = "label_created"
    SHIPPED = "shipped"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    RETURNED = "returned"
    CANCELLED = "cancelled"


# Order Item
class OrderItemCreate(BaseModel):
    variant_id: UUID
    quantity: int = Field(..., ge=1)
    seller_listing_id: Optional[UUID] = None


class OrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    order_id: UUID
    supplier_shop_id: UUID
    variant_id: UUID
    quantity: int
    supplier_price: Decimal
    seller_price: Decimal
    shipping_price: Decimal
    profit: Optional[Decimal]
    status: OrderStatus
    created_at: datetime


# Order
class OrderCreate(BaseModel):
    items: List[OrderItemCreate]
    customer_data: dict = {}
    notes: Optional[str] = None


class OrderUpdate(BaseModel):
    status: Optional[OrderStatus] = None
    notes: Optional[str] = None


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    shop_id: UUID
    external_order_id: Optional[str]
    customer_data: dict
    total_price: Decimal
    shipping_price: Decimal
    discount: Decimal
    status: OrderStatus
    notes: Optional[str]
    confirmed_at: Optional[datetime]
    paid_at: Optional[datetime]
    shipped_at: Optional[datetime]
    delivered_at: Optional[datetime]
    completed_at: Optional[datetime]
    cancelled_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    items: List[OrderItemResponse] = []


# Shipment
class ShipmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    order_id: UUID
    order_item_id: UUID
    tracking_code: Optional[str]
    carrier: Optional[str]
    status: ShipmentStatus
    shipped_at: Optional[datetime]
    delivered_at: Optional[datetime]
    delivery_confirmed_at: Optional[datetime]
    delivery_confirmed_by: Optional[str]
    created_at: datetime


class DeliveryConfirmRequest(BaseModel):
    confirmed_by: str = Field(..., pattern="^(customer|admin)$")


# Order History
class OrderHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    order_id: UUID
    order_item_id: Optional[UUID]
    from_status: Optional[str]
    to_status: str
    actor_type: Optional[str]
    reason: Optional[str]
    created_at: datetime
