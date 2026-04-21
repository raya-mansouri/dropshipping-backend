"""
Pricing Domain Models
=====================
Price history tracking for audit and analytics
"""
from sqlalchemy import Column, String, Numeric, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from datetime import datetime
from uuid import uuid4

from src.core.database import Base, TimestampMixin, UUIDMixin


class PriceHistory(Base, UUIDMixin, TimestampMixin):
    """
    Price history tracking

    Records all price changes for audit and analytics
    """

    __tablename__ = "price_history"

    variant_id = Column(
        PGUUID(as_uuid=True), ForeignKey("supplier_variants.id"), nullable=False
    )
    listing_id = Column(PGUUID(as_uuid=True), ForeignKey("seller_listings.id"))

    # Prices in Toman (whole numbers)
    old_price = Column(Numeric(15, 0), nullable=False)
    new_price = Column(Numeric(15, 0), nullable=False)
    old_supplier_price = Column(Numeric(15, 0))
    new_supplier_price = Column(Numeric(15, 0))

    margin_percent = Column(Numeric(5, 2))
    margin_changed = Column(String(20))  # increased, decreased, unchanged

    change_reason = Column(
        String(50)
    )  # supplier_price_change, margin_change, manual, sync

    __table_args__ = (
        Index("idx_price_history_variant", "variant_id"),
        Index("idx_price_history_listing", "listing_id"),
        Index("idx_price_history_created", "created_at"),
    )
