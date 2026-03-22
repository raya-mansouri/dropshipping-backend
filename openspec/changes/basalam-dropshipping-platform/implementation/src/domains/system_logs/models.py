"""
System Logs Domain Models
=========================
System-wide logging and monitoring
"""

from sqlalchemy import Column, String, DateTime, Text, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from src.core.database import Base, TimestampMixin, UUIDMixin
import uuid


class SystemLog(Base, UUIDMixin, TimestampMixin):
    """
    System log

    General system logging for monitoring and debugging
    """

    __tablename__ = "system_logs"

    level = Column(String(20), nullable=False)  # INFO, WARNING, ERROR, CRITICAL
    service = Column(
        String(50), nullable=False
    )  # sync_worker, webhook_processor, order_service, etc.
    message = Column(Text, nullable=False)
    metadata = Column(JSONB, default=dict)

    created_at = Column(DateTime, nullable=False)

    __table_args__ = (
        Index("idx_system_logs_level", "level"),
        Index("idx_system_logs_service", "service"),
        Index("idx_system_logs_created", "created_at"),
    )
