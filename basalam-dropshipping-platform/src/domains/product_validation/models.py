"""
Product Validation Domain Models
================================
Product validation logging, forbidden keywords, and detection rules.
"""

from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Index, Boolean
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
    )  # forbidden_category, image_quality, price_range, keyword_scan
    status = Column(String(20), nullable=False)  # passed, failed, warning

    error_code = Column(String(50))
    error_message = Column(Text)
    extra_data = Column("metadata", JSONB, default=dict)

    created_at = Column(DateTime, nullable=False)

    # Relationships
    supplier_product = relationship("SupplierProduct")

    __table_args__ = (
        Index("idx_product_validation_product", "supplier_product_id"),
        Index("idx_product_validation_type", "validation_type"),
        Index("idx_product_validation_status", "status"),
        Index("idx_product_validation_created", "created_at"),
    )


class ForbiddenKeyword(Base, UUIDMixin, TimestampMixin):
    """
    Forbidden keywords for product scanning.

    Products with titles/descriptions matching these keywords
    are flagged for review or auto-rejected.
    """
    __tablename__ = "forbidden_keywords"

    keyword = Column(String(500), nullable=False, index=True)
    category = Column(String(50), nullable=False)  # prohibited, restricted, review_required
    language = Column(String(10), default="fa")  # fa, en, ar
    is_active = Column(Boolean, default=True)
    is_regex = Column(Boolean, default=False)
    severity = Column(String(20), default="high")  # low, medium, high, critical
    description = Column(Text)

    created_by = Column(UUID(as_uuid=True))
    updated_by = Column(UUID(as_uuid=True))

    __table_args__ = (
        Index("idx_forbidden_keywords_keyword", "keyword"),
        Index("idx_forbidden_keywords_category", "category"),
        Index("idx_forbidden_keywords_active", "is_active"),
    )


class ForbiddenProductRule(Base, UUIDMixin, TimestampMixin):
    """
    Rules for forbidden product detection beyond keyword matching.

    Includes category-level prohibitions, image moderation rules, etc.
    """
    __tablename__ = "forbidden_product_rules"

    rule_type = Column(String(50), nullable=False)  # forbidden_category, image_check, price_check
    config = Column(JSONB, default=dict)
    is_active = Column(Boolean, default=True)
    description = Column(Text)

    created_by = Column(UUID(as_uuid=True))

    __table_args__ = (
        Index("idx_forbidden_rules_type", "rule_type"),
        Index("idx_forbidden_rules_active", "is_active"),
    )
