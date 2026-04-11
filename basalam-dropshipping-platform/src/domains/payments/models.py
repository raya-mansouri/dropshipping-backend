"""
Payments Domain Models
=====================
Payment escrow, refunds, and payouts

Payment flow per a.md:
- Seller pays → Platform escrow → Delivery confirmed → Supplier payout

Delivery confirmation:
- 72 hours for normal orders
- 7 days for high-value orders
"""
from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, Integer, Numeric, Text, Index
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from src.core.database import Base, TimestampMixin, UUIDMixin
import uuid
from enum import Enum


class PaymentStatus(str, Enum):
    """Payment status"""
    PENDING = "pending"
    SELLER_PAID = "seller_paid"
    ESCROW = "escrow"
    SUPPLIER_PAID = "supplier_paid"
    REFUNDED = "refunded"
    FAILED = "failed"


class Payment(Base, UUIDMixin, TimestampMixin):
    """
    Payment for an order
    
    Tracks payment from seller through escrow to supplier
    """
    __tablename__ = "payments"
    
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False)
    order_item_id = Column(UUID(as_uuid=True), ForeignKey("order_items.id"))
    
    # Amounts
    seller_paid_amount = Column(Numeric(12, 2), nullable=False)
    supplier_payable_amount = Column(Numeric(12, 2), nullable=False)
    platform_fee = Column(Numeric(12, 2), default=0)
    shipping_cost = Column(Numeric(12, 2), default=0)
    
    # Payment gateway
    gateway = Column(String(50))  # stripe, idpay, etc.
    gateway_transaction_id = Column(String(255))
    gateway_refund_id = Column(String(255))
    
    status = Column(String(30), default=PaymentStatus.PENDING.value)
    
    # Timestamps
    paid_at = Column(DateTime(timezone=True))
    escrow_started_at = Column(DateTime(timezone=True))
    supplier_paid_at = Column(DateTime(timezone=True))
    refunded_at = Column(DateTime(timezone=True))
    
    # Failure
    failure_reason = Column(Text)
    failure_code = Column(String(50))
    
    # Metadata
    extra_data = Column("metadata", JSONB, default=dict)
    
    # Relationships
    order = relationship("Order", back_populates="payments")
    order_item = relationship("OrderItem", back_populates="payment")
    refund = relationship("Refund", back_populates="payment", uselist=False)
    payout = relationship("SupplierPayout", back_populates="payment", uselist=False)
    
    __table_args__ = (
        Index('idx_payments_order', 'order_id'),
        Index('idx_payments_status', 'status'),
        Index('idx_payments_gateway', 'gateway_transaction_id'),
    )


class Refund(Base, UUIDMixin, TimestampMixin):
    """
    Refund processing
    
    Can be full or partial
    """
    __tablename__ = "refunds"
    
    order_item_id = Column(UUID(as_uuid=True), ForeignKey("order_items.id"), nullable=False)
    payment_id = Column(UUID(as_uuid=True), ForeignKey("payments.id"))
    
    amount = Column(Numeric(12, 2), nullable=False)
    refund_type = Column(String(20))  # full, partial, shipping
    
    reason = Column(Text)
    status = Column(String(30), default="requested")  # requested, approved, rejected, completed, failed
    
    requested_by = Column(String(20))  # seller, customer, admin
    approved_by = Column(UUID(as_uuid=True))
    rejected_by = Column(UUID(as_uuid=True))
    
    approved_at = Column(DateTime(timezone=True))
    rejected_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    
    gateway_refund_id = Column(String(255))
    
    # Relationships
    order_item = relationship("OrderItem", back_populates="refund")
    payment = relationship("Payment", back_populates="refund")


class SupplierPayout(Base, UUIDMixin, TimestampMixin):
    """
    Supplier payout from escrow
    
    Released after delivery confirmed + dispute window
    """
    __tablename__ = "supplier_payouts"
    
    supplier_id = Column(UUID(as_uuid=True), ForeignKey("shops.id"), nullable=False)
    order_item_id = Column(UUID(as_uuid=True), ForeignKey("order_items.id"), nullable=False)
    payment_id = Column(UUID(as_uuid=True), ForeignKey("payments.id"))
    
    amount = Column(Numeric(12, 2), nullable=False)
    status = Column(String(30), default="pending")  # pending, processing, completed, failed, cancelled
    
    # Release conditions
    release_conditions_met = Column(Boolean, default=False)
    delivery_confirmed_at = Column(DateTime(timezone=True))
    dispute_window_ends_at = Column(DateTime(timezone=True))
    
    # Payout details
    payout_method = Column(String(50))  # wallet, bank_transfer
    payout_reference = Column(String(255))
    
    released_at = Column(DateTime(timezone=True))
    failed_at = Column(DateTime(timezone=True))
    failure_reason = Column(Text)
    
    # Relationships
    payment = relationship("Payment", back_populates="payout")


class Dispute(Base, UUIDMixin, TimestampMixin):
    """
    Dispute between seller and supplier
    
    Freezes payment until resolved
    """
    __tablename__ = "disputes"
    
    order_item_id = Column(UUID(as_uuid=True), ForeignKey("order_items.id"), nullable=False)
    
    opened_by = Column(String(20), nullable=False)  # seller, supplier, customer, admin
    opened_by_id = Column(UUID(as_uuid=True))
    
    reason = Column(Text, nullable=False)
    evidence = Column(JSONB, default=list)  # Screenshots, documents
    
    status = Column(String(30), default="open")  # open, investigating, resolved, rejected
    
    resolution = Column(Text)
    resolved_by = Column(UUID(as_uuid=True))
    resolved_at = Column(DateTime(timezone=True))
    
    # Dispute outcome
    outcome = Column(String(30))  # seller_wins, supplier_wins, partial, cancelled
    outcome_amount = Column(Numeric(12, 2))  # If partial
    
    # Relationships
    order_item = relationship("OrderItem", back_populates="dispute")
    
    __table_args__ = (
        Index('idx_disputes_order_item', 'order_item_id'),
        Index('idx_disputes_status', 'status'),
    )
