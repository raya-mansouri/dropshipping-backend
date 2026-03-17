"""
Integration Logs Domain Models
===============================
Integration sync and API call logging
"""

from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Index
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from src.core.database import Base, TimestampMixin, UUIDMixin
import uuid


class IntegrationLog(Base, UUIDMixin, TimestampMixin):
    """
    Integration sync and API call logs

    Tracks all integration activities for debugging and monitoring
    """

    __tablename__ = "integration_logs"

    integration_id = Column(
        UUID(as_uuid=True), ForeignKey("shop_integrations.id"), nullable=False
    )

    action = Column(
        String(50), nullable=False
    )  # sync_start, sync_end, api_call, webhook_received
    status = Column(String(20), nullable=False)  # success, failed

    request_data = Column(JSONB, default=dict)
    response_data = Column(JSONB, default=dict)
    error_message = Column(Text)

    created_at = Column(DateTime, nullable=False)

    # Relationships
    integration = relationship("ShopIntegration")

    __table_args__ = (
        Index("idx_integration_logs_integration", "integration_id"),
        Index("idx_integration_logs_action", "action"),
        Index("idx_integration_logs_status", "status"),
        Index("idx_integration_logs_created", "created_at"),
    )
