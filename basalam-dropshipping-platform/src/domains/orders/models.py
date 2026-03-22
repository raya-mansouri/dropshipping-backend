"""
Orders Domain Models
====================
Order lifecycle, items, state machine

Order states per a.md:
- pending → confirmed → paid → processing → shipped → delivered → completed
- Failure states: cancelled, disputed, refunded
"""
from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, Integer, Numeric, Text, Index
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from src.core.database import Base, TimestampMixin, UUIDMixin
import uuid
from enum import Enum


class OrderStatus(str, Enum):
    """Order status states"""
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


class Order(Base, UUIDMixin, TimestampMixin):
    """
    Main order table
    
    An order can have items from multiple suppliers
    """
    __tablename__ = "orders"
    
    platform_id = Column(UUID(as_uuid=True), ForeignKey("platforms.id"))
    external_order_id = Column(String(255))  # Order ID on seller's platform
    
    shop_id = Column(UUID(as_uuid=True), ForeignKey("shops.id"), nullable=False)
    
    customer_data = Column(JSONB, default=dict)  # Customer info
    
    total_price = Column(Numeric(12, 2), nullable=False)  # Total customer paid
    shipping_price = Column(Numeric(12, 2), default=0)
    discount = Column(Numeric(12, 2), default=0)
    
    status = Column(String(30), default=OrderStatus.PENDING.value)
    
    # Metadata
    notes = Column(Text)
    extra_data = Column("metadata", JSONB, default=dict)
    
    # Timestamps
    confirmed_at = Column(DateTime)
    paid_at = Column(DateTime)
    shipped_at = Column(DateTime)
    delivered_at = Column(DateTime)
    completed_at = Column(DateTime)
    cancelled_at = Column(DateTime)
    
    # Relationships
    shop = relationship("Shop", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="order")
    shipments = relationship("Shipment", back_populates="order")
    
    __table_args__ = (
        Index('idx_orders_shop', 'shop_id'),
        Index('idx_orders_status', 'status'),
        Index('idx_orders_external', 'external_order_id'),
        Index('idx_orders_created', 'created_at'),
    )


class OrderItem(Base, UUIDMixin, TimestampMixin):
    """
    Order item
    
    Each item has price snapshot at order time
    """
    __tablename__ = "order_items"
    
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False)
    supplier_shop_id = Column(UUID(as_uuid=True), ForeignKey("shops.id"), nullable=False)
    
    variant_id = Column(UUID(as_uuid=True), ForeignKey("product_variants.id"), nullable=False)
    seller_listing_id = Column(UUID(as_uuid=True), ForeignKey("seller_listings.id"))
    
    quantity = Column(Integer, nullable=False)
    
    # Price snapshot - CRITICAL per a.md
    supplier_price = Column(Numeric(12, 2), nullable=False)  # At order time
    seller_price = Column(Numeric(12, 2), nullable=False)  # At order time
    shipping_price = Column(Numeric(12, 2), default=0)
    
    profit = Column(Numeric(12, 2))  # seller_price - supplier_price
    
    status = Column(String(30), default=OrderStatus.PENDING.value)
    
    # Rejection reason
    reject_reason = Column(String(255))
    rejected_at = Column(DateTime)
    
    # Relationships
    order = relationship("Order", back_populates="items")
    variant = relationship("ProductVariant", back_populates="order_items")
    inventory_reservation = relationship("InventoryReservation", back_populates="order_item", uselist=False)
    shipments = relationship("Shipment", back_populates="order_item")
    payment = relationship("Payment", back_populates="order_item")
    dispute = relationship("Dispute", back_populates="order_item", uselist=False)
    refund = relationship("Refund", back_populates="order_item", uselist=False)
    
    __table_args__ = (
        Index('idx_order_items_order', 'order_id'),
        Index('idx_order_items_supplier', 'supplier_shop_id'),
        Index('idx_order_items_variant', 'variant_id'),
    )


class OrderHistory(Base, UUIDMixin):
    """
    Order status change history
    
    Audit trail for order lifecycle
    """
    __tablename__ = "order_history"
    
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False)
    order_item_id = Column(UUID(as_uuid=True), ForeignKey("order_items.id"))
    
    from_status = Column(String(30))
    to_status = Column(String(30), nullable=False)
    
    actor_type = Column(String(30))  # system, seller, supplier, customer, admin
    actor_id = Column(UUID(as_uuid=True))
    
    reason = Column(Text)
    extra_data = Column("metadata", JSONB, default=dict)
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class Shipment(Base, UUIDMixin, TimestampMixin):
    """
    Shipment tracking
    
    Created when order is paid and sent to supplier
    """
    __tablename__ = "shipments"
    
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False)
    order_item_id = Column(UUID(as_uuid=True), ForeignKey("order_items.id"), nullable=False)
    
    shipping_method_id = Column(UUID(as_uuid=True), ForeignKey("shipping_methods.id"))
    
    tracking_code = Column(String(255))
    carrier = Column(String(100))
    
    status = Column(String(30), default="pending")  # pending, label_created, shipped, in_transit, delivered, returned, cancelled
    
    shipped_at = Column(DateTime)
    delivered_at = Column(DateTime)
    
    # Delivery confirmation
    delivery_confirmed_at = Column(DateTime)
    delivery_confirmed_by = Column(String(20))  # carrier, customer, auto
    
    estimated_delivery = Column(DateTime)
    actual_delivery = Column(DateTime)
    
    # Relationships
    order = relationship("Order", back_populates="shipments")
    order_item = relationship("OrderItem", back_populates="shipments")
    
    __table_args__ = (
        Index('idx_shipments_order', 'order_id'),
        Index('idx_shipments_tracking', 'tracking_code'),
    )
