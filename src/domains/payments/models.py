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

from sqlalchemy import (
    Column,
    String,
    DateTime,
    Boolean,
    ForeignKey,
    Numeric,
    Text,
    Index,
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from src.core.database import Base, TimestampMixin, UUIDMixin
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

    # Amounts in Toman
    seller_paid_amount = Column(Numeric(15, 0), nullable=False)
    supplier_payable_amount = Column(Numeric(15, 0), nullable=False)
    platform_fee = Column(Numeric(15, 0), default=0)
    shipping_cost = Column(Numeric(15, 0), default=0)

    # Payment gateway (Iranian: idpay, zarinpal, etc.)
    gateway = Column(String(50))
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
        Index("idx_payments_order", "order_id"),
        Index("idx_payments_status", "status"),
        Index("idx_payments_gateway", "gateway_transaction_id"),
    )


class Refund(Base, UUIDMixin, TimestampMixin):
    """
    Refund processing

    Can be full or partial
    """

    __tablename__ = "refunds"

    order_item_id = Column(
        UUID(as_uuid=True), ForeignKey("order_items.id"), nullable=False
    )
    payment_id = Column(UUID(as_uuid=True), ForeignKey("payments.id"))

    amount = Column(Numeric(15, 0), nullable=False)  # Toman
    refund_type = Column(String(20))  # full, partial, shipping

    reason = Column(Text)
    status = Column(
        String(30), default="requested"
    )  # requested, approved, rejected, completed, failed

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
    order_item_id = Column(
        UUID(as_uuid=True), ForeignKey("order_items.id"), nullable=False
    )
    payment_id = Column(UUID(as_uuid=True), ForeignKey("payments.id"))

    amount = Column(Numeric(15, 0), nullable=False)  # Toman
    status = Column(
        String(30), default="pending"
    )  # pending, processing, completed, failed, cancelled

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


class TransactionType(str, Enum):
    """Wallet transaction types"""

    DEPOSIT = "deposit"
    ORDER_PAYMENT = "order_payment"
    SHIPPING = "shipping"
    COMMISSION = "commission"
    REFUND = "refund"
    PAYOUT = "payout"


class TransactionStatus(str, Enum):
    """Wallet transaction status"""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class WalletTransaction(Base, UUIDMixin, TimestampMixin):
    """
    Wallet transaction ledger

    Records all wallet movements: deposits, order payments, refunds, payouts.
    Balance is calculated as SUM(amount) for a user's completed transactions.
    """

    __tablename__ = "wallet_transactions"

    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )

    amount = Column(
        Numeric(15, 0), nullable=False
    )  # Positive for deposits/refunds, negative for payments
    type = Column(
        String(30), nullable=False
    )  # deposit, order_payment, shipping, commission, refund, payout

    status = Column(
        String(30),
        nullable=False,
        default=TransactionStatus.PENDING.value,
        server_default=TransactionStatus.PENDING.value,
    )

    # Reference linking (polymorphic)
    reference_type = Column(String(50))  # payment, order, payout
    reference_id = Column(String(255))  # Gateway authority / order ID / payout ID

    description = Column(Text)

    # Gateway metadata
    gateway = Column(String(50))
    gateway_ref_id = Column(String(255))  # Gateway reference ID after verification
    extra_data = Column("metadata", JSONB, default=dict)

    __table_args__ = (
        Index("idx_wallet_type", "type"),
        Index("idx_wallet_reference", "reference_type", "reference_id"),
        Index("idx_wallet_status", "status"),
        CheckConstraint("amount != 0", name="ck_wallet_nonzero_amount"),
        CheckConstraint(
            "CASE WHEN type IN ('deposit', 'refund') THEN amount > 0 ELSE amount < 0 END",
            name="ck_wallet_amount_sign",
        ),
    )


class Dispute(Base, UUIDMixin, TimestampMixin):
    """
    Dispute between seller and supplier

    Freezes payment until resolved
    """

    __tablename__ = "disputes"

    order_item_id = Column(
        UUID(as_uuid=True), ForeignKey("order_items.id"), nullable=False
    )

    opened_by = Column(String(20), nullable=False)  # seller, supplier, customer, admin
    opened_by_id = Column(UUID(as_uuid=True))

    reason = Column(Text, nullable=False)
    evidence = Column(JSONB, default=list)  # Screenshots, documents

    status = Column(
        String(30), default="open"
    )  # open, investigating, resolved, rejected

    resolution = Column(Text)
    resolved_by = Column(UUID(as_uuid=True))
    resolved_at = Column(DateTime(timezone=True))

    # Dispute outcome
    outcome = Column(String(30))  # seller_wins, supplier_wins, partial, cancelled
    outcome_amount = Column(Numeric(15, 0))  # Toman, if partial dispute

    # Relationships
    order_item = relationship("OrderItem", back_populates="dispute")

    __table_args__ = (
        Index("idx_disputes_order_item", "order_item_id"),
        Index("idx_disputes_status", "status"),
    )
