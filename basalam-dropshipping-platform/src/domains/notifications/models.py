"""
Notifications Domain Models
==========================
In-app, SMS, and webhook notifications
"""
from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, Integer, Text, Index, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from src.core.database import Base, TimestampMixin, UUIDMixin
import uuid
from enum import Enum


class NotificationChannel(str, Enum):
    """Notification delivery channel"""
    SMS = "sms"
    IN_APP = "in_app"
    WEBHOOK = "webhook"


class NotificationStatus(str, Enum):
    """Notification delivery status"""
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    READ = "read"


class Notification(Base, UUIDMixin, TimestampMixin):
    """
    In-app notification
    
    Stored in database, delivered via API
    """
    __tablename__ = "notifications"
    
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    type = Column(String(50), nullable=False)  # order_created, payment_received, etc.
    
    title = Column(String(255), nullable=False)
    body = Column(Text)
    
    action_url = Column(String(500))
    action_type = Column(String(50))  # view_order, view_product, etc.
    
    payload = Column(JSONB, default=dict)  # Additional data
    
    status = Column(String(20), default=NotificationStatus.PENDING.value)
    
    read_at = Column(DateTime)
    read_by = Column(UUID(as_uuid=True))
    
    # Relationships
    user = relationship("User", back_populates="notifications")
    
    __table_args__ = (
        Index('idx_notifications_user', 'user_id'),
        Index('idx_notifications_status', 'status'),
        Index('idx_notifications_type', 'type'),
    )


class NotificationPreference(Base, UUIDMixin, TimestampMixin):
    """
    User notification preferences
    
    Controls which notifications user receives and via which channel
    """
    __tablename__ = "notification_preferences"
    
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Event types
    event_type = Column(String(50), nullable=False)  # order_created, inventory_low, etc.
    
    # Channels enabled for this event
    sms_enabled = Column(Boolean, default=False)
    in_app_enabled = Column(Boolean, default=True)
    webhook_enabled = Column(Boolean, default=False)
    
    # Quiet hours
    quiet_hours_enabled = Column(Boolean, default=False)
    quiet_hours_start = Column(String(5))  # "22:00"
    quiet_hours_end = Column(String(5))    # "08:00"
    
    __table_args__ = (
        UniqueConstraint('user_id', 'event_type', name='uq_user_event_preference'),
    )


class NotificationLog(Base, UUIDMixin):
    """
    Log of all sent notifications
    
    For audit and debugging
    """
    __tablename__ = "notification_logs"
    
    notification_id = Column(UUID(as_uuid=True), ForeignKey("notifications.id"))
    
    channel = Column(String(20), nullable=False)  # sms, webhook
    
    recipient = Column(String(255))  # phone, or webhook URL
    
    status = Column(String(20), default=NotificationStatus.PENDING.value)
    
    provider = Column(String(50))  # sendgrid, kavenegar, twilio
    provider_message_id = Column(String(255))  # Message ID from provider
    
    error = Column(Text)
    error_code = Column(String(50))
    
    sent_at = Column(DateTime)
    delivered_at = Column(DateTime)
    
    cost = Column(Integer, nullable=False)  # SMS cost etc.
    
    __table_args__ = (
        Index('idx_notification_logs_notification', 'notification_id'),
        Index('idx_notification_logs_status', 'status'),
    )
