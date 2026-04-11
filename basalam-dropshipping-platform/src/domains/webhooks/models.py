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
from datetime import datetime, timezone
from enum import Enum


class WebhookEventLog(Base, UUIDMixin, TimestampMixin):
    """
    Event store log for domain events

    Persisted copy of every domain event for replay and audit.
    """
    __tablename__ = "webhook_event_logs"

    platform_id = Column(String(100), nullable=False)
    event_id = Column(String(255), nullable=False)
    payload_hash = Column(String(64), nullable=True)
    processed_at = Column(DateTime)
    extra_data = Column("metadata", JSONB, nullable=True)

    __table_args__ = (
        Index('ix_webhook_event_logs_platform', 'platform_id'),
        Index('ix_webhook_event_logs_created', 'created_at'),
        UniqueConstraint('platform_id', 'event_id', name='uq_webhook_event_logs_platform_event'),
    )


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
    
    processed_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
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


class OutgoingWebhookStatus(str, Enum):
    """Outgoing webhook status"""
    PENDING = "pending"
    SENT = "sent"
    RETRYING = "retrying"
    FAILED = "failed"
    DLQ = "dlq"


class OutgoingWebhookLog(Base, UUIDMixin, TimestampMixin):
    """
    Outgoing webhook log

    Tracks webhooks sent to external seller/supplier systems
    """
    __tablename__ = "outgoing_webhook_logs"

    integration_id = Column(UUID(as_uuid=True), ForeignKey("shop_integrations.id"), nullable=False)
    event_type = Column(String(100), nullable=False)  # order.created, order.shipped, inventory.updated

    payload = Column(JSONB, nullable=False)
    url = Column(String(2048), nullable=False)

    status = Column(String(20), default=OutgoingWebhookStatus.PENDING.value)

    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=5)

    last_attempt_at = Column(DateTime)
    next_retry_at = Column(DateTime)

    last_error = Column(Text)
    response_status_code = Column(Integer)
    response_body = Column(Text)

    # Relationships
    integration = relationship("ShopIntegration")

    __table_args__ = (
        Index('idx_outgoing_webhook_logs_integration', 'integration_id'),
        Index('idx_outgoing_webhook_logs_status', 'status'),
        Index('idx_outgoing_webhook_logs_retry', 'next_retry_at'),
    )


class OutgoingWebhookDLQ(Base, UUIDMixin, TimestampMixin):
    """
    Dead letter queue for failed outgoing webhooks

    Requires manual intervention or automatic cleanup
    """
    __tablename__ = "outgoing_webhook_dlq"

    outgoing_webhook_log_id = Column(UUID(as_uuid=True), ForeignKey("outgoing_webhook_logs.id"), nullable=False)

    failure_reason = Column(Text, nullable=False)
    failure_count = Column(Integer, default=0)

    status = Column(String(20), default="pending")  # pending, investigation, resolved
    resolved_at = Column(DateTime)
    resolved_by = Column(UUID(as_uuid=True))
    resolution_notes = Column(Text)

    # Relationships
    outgoing_webhook_log = relationship("OutgoingWebhookLog")

    __table_args__ = (
        Index('idx_outgoing_webhook_dlq_status', 'status'),
    )
