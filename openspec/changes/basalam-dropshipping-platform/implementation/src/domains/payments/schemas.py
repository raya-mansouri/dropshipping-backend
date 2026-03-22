"""
Payments Domain Schemas
========================
Pydantic schemas for payments API
"""
from pydantic import BaseModel, Field, ConfigDict
from uuid import UUID
from datetime import datetime
from typing import Optional, List
from decimal import Decimal
from enum import Enum


class PaymentStatus(str, Enum):
    PENDING = "pending"
    SELLER_PAID = "seller_paid"
    ESCROW = "escrow"
    SUPPLIER_PAID = "supplier_paid"
    REFUNDED = "refunded"
    FAILED = "failed"


class RefundStatus(str, Enum):
    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"
    FAILED = "failed"


class DisputeStatus(str, Enum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    REJECTED = "rejected"


# Payment
class PaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    order_id: UUID
    order_item_id: Optional[UUID]
    seller_paid_amount: Decimal
    supplier_payable_amount: Decimal
    platform_fee: Decimal
    shipping_cost: Decimal
    gateway: Optional[str]
    gateway_transaction_id: Optional[str]
    status: PaymentStatus
    paid_at: Optional[datetime]
    escrow_started_at: Optional[datetime]
    supplier_paid_at: Optional[datetime]
    refunded_at: Optional[datetime]
    failure_reason: Optional[str]
    created_at: datetime


# Refund
class RefundCreate(BaseModel):
    amount: Optional[Decimal] = None  # If null, full refund
    refund_type: str = Field(..., pattern="^(full|partial|shipping)$")
    reason: str
    requested_by: str = Field(..., pattern="^(seller|customer|admin)$")


class RefundResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    order_item_id: UUID
    payment_id: Optional[UUID]
    amount: Decimal
    refund_type: str
    reason: str
    status: RefundStatus
    requested_by: str
    approved_by: Optional[UUID]
    rejected_by: Optional[UUID]
    approved_at: Optional[datetime]
    rejected_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime


class RefundApproveRequest(BaseModel):
    approved: bool
    notes: Optional[str] = None


# Dispute
class DisputeCreate(BaseModel):
    reason: str
    evidence: List[dict] = []  # URLs to evidence files


class DisputeUpdate(BaseModel):
    status: Optional[DisputeStatus] = None
    resolution: Optional[str] = None
    outcome: Optional[str] = Field(None, pattern="^(seller_wins|supplier_wins|partial|cancelled)$")
    outcome_amount: Optional[Decimal] = None


class DisputeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    order_item_id: UUID
    opened_by: str
    reason: str
    evidence: List[dict]
    status: DisputeStatus
    resolution: Optional[str]
    resolved_by: Optional[UUID]
    resolved_at: Optional[datetime]
    outcome: Optional[str]
    outcome_amount: Optional[Decimal]
    created_at: datetime


# Supplier Payout
class SupplierPayoutResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    supplier_id: UUID
    order_item_id: UUID
    payment_id: Optional[UUID]
    amount: Decimal
    status: str
    delivery_confirmed_at: Optional[datetime]
    dispute_window_ends_at: Optional[datetime]
    released_at: Optional[datetime]
    failure_reason: Optional[str]
    created_at: datetime


# Payment Initialize
class PaymentInitializeRequest(BaseModel):
    order_id: UUID
    gateway: str = "idpay"  # Default gateway


class PaymentInitializeResponse(BaseModel):
    payment_id: UUID
    payment_url: str
    gateway_transaction_id: str
