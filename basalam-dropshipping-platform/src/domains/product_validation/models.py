"""
Product Validation Domain Models
================================
Product validation logging and rules
"""

from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Index
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from src.core.database import Base, TimestampMixin, UUIDMixin
import uuid


class ProductValidationLog(Base, UUIDMixin, TimestampMixin):
    """
    Product validation log

    Tracks validation results for supplier products
    """

    __tablename__ = "product_validation_logs"

    supplier_product_id = Column(
        UUID(as_uuid=True), ForeignKey("supplier_products.id"), nullable=False
    )

    validation_type = Column(
        String(50), nullable=False
    )  # forbidden_category, image_quality, price_range
    status = Column(String(20), nullable=False)  # passed, failed, warning

    error_code = Column(String(50))
    error_message = Column(Text)
    metadata = Column(JSONB, default=dict)

    created_at = Column(DateTime, nullable=False)

    # Relationships
    supplier_product = relationship("SupplierProduct")

    __table_args__ = (
        Index("idx_product_validation_product", "supplier_product_id"),
        Index("idx_product_validation_type", "validation_type"),
        Index("idx_product_validation_status", "status"),
        Index("idx_product_validation_created", "created_at"),
    )
