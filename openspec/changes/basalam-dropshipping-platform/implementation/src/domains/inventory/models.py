"""
Inventory Domain Models
=======================
Inventory management, reservations, and tracking

Key concepts per a.md:
- Supplier inventory = source of truth
- Atomic reservation for orders
- Reconciliation jobs
"""
from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, Integer, Numeric, Text
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from src.core.database import Base, TimestampMixin, UUIDMixin
import uuid
from datetime import datetime, timedelta
from enum import Enum


class InventoryReservation(Base, UUIDMixin, TimestampMixin):
    """
    Inventory reservation for orders
    
    Prevents overselling when multiple orders come in simultaneously
    """
    __tablename__ = "inventory_reservations"
    
    variant_id = Column(UUID(as_uuid=True), ForeignKey("supplier_variants.id"), nullable=False)
    order_item_id = Column(UUID(as_uuid=True), ForeignKey("order_items.id"), nullable=False)
    
    quantity = Column(Integer, nullable=False)
    status = Column(String(20), default="reserved")  # reserved, released, consumed
    
    expires_at = Column(DateTime, nullable=False)  # Reservation expires if not paid
    
    released_at = Column(DateTime)
    released_reason = Column(String(50))  # payment_timeout, cancelled, manually_released
    
    # Relationships
    variant = relationship("SupplierVariant", back_populates="reservations")
    order_item = relationship("OrderItem", back_populates="inventory_reservation")
    
    __table_args__ = (
        Index('idx_inventory_reservations_variant', 'variant_id'),
        Index('idx_inventory_reservations_expires', 'expires_at'),
        Index('idx_inventory_reservations_order_item', 'order_item_id'),
    )


class InventoryLog(Base, UUIDMixin):
    """
    Inventory change history
    
    Audit trail for all inventory changes
    """
    __tablename__ = "inventory_logs"
    
    variant_id = Column(UUID(as_uuid=True), ForeignKey("supplier_variants.id"), nullable=False)
    
    old_inventory = Column(Integer, nullable=False)
    new_inventory = Column(Integer, nullable=False)
    change = Column(Integer, nullable=False)  # new - old
    
    source = Column(String(30), nullable=False)  # webhook, manual, order, reconciliation, correction
    reference_id = Column(UUID(as_uuid=True))  # order_id, sync_job_id, etc.
    reference_type = Column(String(50))  # order, sync_job, manual
    
    reason = Column(Text)
    metadata = Column(JSONB, default=dict)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    variant = relationship("SupplierVariant", back_populates="inventory_logs")
    
    __table_args__ = (
        Index('idx_inventory_logs_variant', 'variant_id'),
        Index('idx_inventory_logs_created', 'created_at'),
    )


class InventoryReconciliation(Base, UUIDMixin, TimestampMixin):
    """
    Reconciliation job results
    
    Tracks periodic inventory reconciliation with supplier
    """
    __tablename__ = "inventory_reconciliations"
    
    integration_id = Column(UUID(as_uuid=True), ForeignKey("shop_integrations.id"))
    
    status = Column(String(30), default="pending")  # pending, running, completed, failed
    total_variants = Column(Integer, default=0)
    matched_count = Column(Integer, default=0)
    mismatch_count = Column(Integer, default=0)
    fixed_count = Column(Integer, default=0)
    
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    
    errors = Column(JSONB, default=list)
    details = Column(JSONB, default=list)  # List of mismatches
    
    # Relationships
    integration = relationship("ShopIntegration")


# ============================================
# INVENTORY STATUS ENUM
# ============================================

class InventorySource(str, Enum):
    WEBHOOK = "webhook"
    MANUAL = "manual"
    ORDER = "order"
    RECONCILIATION = "reconciliation"
    CORRECTION = "correction"
