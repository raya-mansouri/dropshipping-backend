"""
Webhooks Domain Models
=======================
Webhook events, processing, and idempotency

Webhook reliability per a.md:
- Idempotency with UNIQUE constraint
- Retry schedule: 1m, 5m, 15m, 1h, 6h
- Dead letter queue for failed events
"""
from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, Integer, Text, Index, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from src.core.database import Base, TimestampMixin, UUIDMixin
import uuid
from datetime import datetime
from enum import Enum


class WebhookEventStatus(str, Enum):
    """Webhook processing status"""
    RECEIVED = "received"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    DLQ = "dlq"  # Dead letter queue


class WebhookEvent(Base, UUIDMixin, TimestampMixin):
    """
    Incoming webhook event
    
    Stores raw event for processing and replay
    """
    __tablename__ = "webhook_events"
    
    platform_id = Column(UUID(as_uuid=True), ForeignKey("platforms.id"), nullable=False)
    integration_id = Column(UUID(as_uuid=True), ForeignKey("shop_integrations.id"))
    
    event_type = Column(String(100), nullable=False)  # order.created, product.updated, etc.
    external_event_id = Column(String(255), nullable=False)  # ID from platform
    
    payload = Column(JSONB, nullable=False)  # Raw webhook payload
    signature = Column(String(255))  # For verification
    signature_verified = Column(Boolean, default=False)
    
    status = Column(String(30), default=WebhookEventStatus.RECEIVED.value)
    
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=5)
    
    error_message = Column(Text)
    error_trace = Column(Text)
    
    processed_at = Column(DateTime)
    
    # Event data extracted
    entity_type = Column(String(50))  # order, product, inventory
    entity_id = Column(String(255))  # External ID
    
    # Relationships
    platform = relationship("Platform")
    integration = relationship("ShopIntegration")
    
    __table_args__ = (
        Index('idx_webhook_events_platform', 'platform_id'),
        Index('idx_webhook_events_type', 'event_type'),
        Index('idx_webhook_events_status', 'status'),
        Index('idx_webhook_events_entity', 'entity_type', 'entity_id'),
        UniqueConstraint('platform_id', 'external_event_id', name='uq_webhook_platform_event'),
    )


class ProcessedEvent(Base):
    """
    Idempotency tracking
    
    Ensures webhook is only processed once
    """
    __tablename__ = "processed_events"
    
    event_id = Column(String(255), primary_key=True)  # platform + event ID
    event_hash = Column(String(64))  # SHA256 of payload for dedup
    platform_id = Column(UUID(as_uuid=True), ForeignKey("platforms.id"), nullable=False)
    
    processed_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    processed_by = Column(String(50), default="webhook_processor")
    
    __table_args__ = (
        Index('idx_processed_events_platform', 'platform_id'),
    )


class WebhookRetrySchedule(Base, UUIDMixin):
    """
    Retry schedule for failed webhooks
    
    Follows: 1m, 5m, 15m, 1h, 6h (5 attempts)
    """
    __tablename__ = "webhook_retry_schedules"
    
    webhook_event_id = Column(UUID(as_uuid=True), ForeignKey("webhook_events.id"), nullable=False)
    
    attempt = Column(Integer, nullable=False)
    scheduled_at = Column(DateTime, nullable=False)
    
    executed_at = Column(DateTime)
    status = Column(String(20), default="pending")  # pending, executed, failed
    
    error = Column(Text)
    
    __table_args__ = (
        Index('idx_webhook_retry_schedules_event', 'webhook_event_id'),
        Index('idx_webhook_retry_schedules_scheduled', 'scheduled_at'),
    )


class WebhookDeadLetter(Base, UUIDMixin, TimestampMixin):
    """
    Dead letter queue for failed webhooks
    
    Requires manual intervention
    """
    __tablename__ = "webhook_dead_letter"
    
    webhook_event_id = Column(UUID(as_uuid=True), ForeignKey("webhook_events.id"), nullable=False)
    
    original_event_type = Column(String(100))
    payload = Column(JSONB)
    
    failure_reason = Column(Text, nullable=False)
    failure_count = Column(Integer, default=0)
    
    status = Column(String(20), default="pending")  # pending, investigation, resolved
    
    resolved_by = Column(UUID(as_uuid=True))
    resolution_notes = Column(Text)
    
    # Relationships
    webhook_event = relationship("WebhookEvent")
    
    __table_args__ = (
        Index('idx_webhook_dead_letter_status', 'status'),
    )
