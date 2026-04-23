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
    seller_paid_amount: Decimal = Field(description="Amount paid by seller in Toman")
    supplier_payable_amount: Decimal = Field(
        description="Amount payable to supplier in Toman"
    )
    platform_fee: Decimal = Field(description="Platform fee in Toman")
    shipping_cost: Decimal = Field(description="Shipping cost in Toman")
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
    amount: Optional[Decimal] = Field(
        None, description="Refund amount in Toman (null = full refund)"
    )
    refund_type: str = Field(..., pattern="^(full|partial|shipping)$")
    reason: str
    requested_by: str = Field(..., pattern="^(seller|customer|admin)$")


class RefundResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    order_item_id: UUID
    payment_id: Optional[UUID]
    amount: Decimal = Field(description="Refund amount in Toman")
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
    outcome: Optional[str] = Field(
        None, pattern="^(seller_wins|supplier_wins|partial|cancelled)$"
    )
    outcome_amount: Optional[Decimal] = Field(
        None, description="Partial dispute outcome amount in Toman"
    )


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
    amount: Decimal = Field(description="Payout amount in Toman")
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


# ---- Wallet Schemas ----


class WalletDepositRequest(BaseModel):
    """Request to initiate a wallet deposit via payment gateway."""

    amount: int = Field(..., gt=0, description="Amount in Toman to deposit")


class WalletDepositResponse(BaseModel):
    """Response after initiating a wallet deposit."""

    transaction_id: UUID
    payment_url: str = Field(description="URL to redirect user to payment gateway")


class ZarinpalCallbackRequest(BaseModel):
    """Zarinpal payment gateway callback parameters."""

    Authority: str = Field(..., description="Zarinpal authority token")
    Status: Literal["OK", "NOK"] = Field(..., description="OK or NOK from gateway")


class WalletBalanceResponse(BaseModel):
    """Current wallet balance for a user."""

    user_id: UUID
    balance: int = Field(description="Current wallet balance in Toman")
    pending_amount: int = Field(default=0, description="Amount in pending transactions")


class PayOrderRequest(BaseModel):
    """Request to pay an order from wallet."""

    order_id: UUID


class PayOrderResponse(BaseModel):
    """Response after paying an order from wallet."""

    payment_id: UUID
    order_id: UUID
    total_paid: int = Field(description="Total amount deducted from wallet")
    breakdown: dict = Field(default_factory=dict, description="Cost breakdown")


class WalletTransactionResponse(BaseModel):
    """Single wallet transaction."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    amount: Decimal
    type: str
    status: str
    description: Optional[str] = None
    reference_type: Optional[str] = None
    reference_id: Optional[str] = None
    gateway_ref_id: Optional[str] = None
    created_at: datetime
