"""
Fraud Detection Domain Models
=============================
Fraud signal detection and tracking
"""

from sqlalchemy import Column, String, DateTime, Text, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from src.core.database import Base, TimestampMixin, UUIDMixin
import uuid


class FraudSignal(Base, UUIDMixin, TimestampMixin):
    """
    Fraud signal

    Detected fraud signals for investigation
    """

    __tablename__ = "fraud_signals"

    entity_type = Column(String(50), nullable=False)  # order, seller, supplier
    entity_id = Column(UUID(as_uuid=True), nullable=False)

    signal_type = Column(
        String(50), nullable=False
    )  # high_order_frequency, suspicious_price, inventory_manipulation
    severity = Column(String(20), nullable=False)  # low, medium, high, critical

    data = Column(JSONB, default=dict)
    status = Column(
        String(20), nullable=False
    )  # new, investigating, resolved, false_positive

    created_at = Column(DateTime(timezone=True), nullable=False)
    resolved_at = Column(DateTime(timezone=True))

    __table_args__ = (
        Index("idx_fraud_signals_entity", "entity_type", "entity_id"),
        Index("idx_fraud_signals_type", "signal_type"),
        Index("idx_fraud_signals_severity", "severity"),
        Index("idx_fraud_signals_status", "status"),
        Index("idx_fraud_signals_created", "created_at"),
    )
