"""
Notification Integration Ports - Hexagonal Architecture
=====================================================
This is the PRIMARY ADAPTER interface.
All notification types (SMS, Email, In-App, Webhook) implement this port.
"""
from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, EmailStr
from enum import Enum


# ============================================
# NOTIFICATION TYPES
# ============================================

class NotificationChannel(str, Enum):
    """Available notification channels"""
    EMAIL = "email"
    SMS = "sms"
    IN_APP = "in_app"
    WEBHOOK = "webhook"


class NotificationPriority(str, Enum):
    """Notification priority levels"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


# ============================================
# NOTIFICATION MODELS
# ============================================

class NotificationContent(BaseModel):
    """Content of a notification"""
    title: str
    body: str
    template_id: Optional[str] = None
    variables: Dict[str, Any] = {}  # For template variables
    action_url: Optional[str] = None  # Clickable action


class NotificationRecipient(BaseModel):
    """Recipient information for notification"""
    user_id: Optional[UUID] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    webhook_url: Optional[str] = None


class NotificationRequest(BaseModel):
    """Complete notification request"""
    channel: NotificationChannel
    recipient: NotificationRecipient
    content: NotificationContent
    priority: NotificationPriority = NotificationPriority.NORMAL
    scheduled_at: Optional[datetime] = None
    metadata: Dict[str, Any] = {}


class NotificationResponse(BaseModel):
    """Response from notification provider"""
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None
    provider: str
    sent_at: datetime = Field(default_factory=datetime.utcnow)


# ============================================
# NOTIFICATION PORT (Primary Port)
# ============================================

class NotificationPort(ABC):
    """
    PRIMARY PORT - Abstract interface for notification adapters
    
    All notification adapters (Email, SMS, In-App, Webhook) MUST implement this port.
    """
    
    @property
    @abstractmethod
    def channel(self) -> NotificationChannel:
        """The channel this adapter handles"""
        pass
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the notification provider"""
        pass
    
    @abstractmethod
    async def send(self, request: NotificationRequest) -> NotificationResponse:
        """
        Send notification
        Returns success/failure response
        """
        pass
    
    @abstractmethod
    async def send_batch(self, requests: List[NotificationRequest]) -> List[NotificationResponse]:
        """
        Send multiple notifications
        Optimized for bulk sending
        """
        pass
    
    @abstractmethod
    async def verify_connection(self) -> bool:
        """Verify provider connection is working"""
        pass
    
    @abstractmethod
    async def get_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        """Get notification template by ID"""
        pass


# ============================================
# NOTIFICATION MANAGER PORT
# ============================================

class NotificationManagerPort(ABC):
    """
    PORT - Manages all notification channels
    
    Provides unified interface for sending notifications
    across multiple channels.
    """
    
    @abstractmethod
    async def send(
        self,
        channel: NotificationChannel,
        recipient: NotificationRecipient,
        content: NotificationContent,
        priority: NotificationPriority = NotificationPriority.NORMAL
    ) -> NotificationResponse:
        """Send notification via specific channel"""
        pass
    
    @abstractmethod
    async def send_multi_channel(
        self,
        channels: List[NotificationChannel],
        recipient: NotificationRecipient,
        content: NotificationContent,
        priority: NotificationPriority = NotificationPriority.NORMAL
    ) -> List[NotificationResponse]:
        """Send same notification to multiple channels"""
        pass
    
    @abstractmethod
    async def notify_event(
        self,
        event_type: str,
        recipient: NotificationRecipient,
        event_data: Dict[str, Any]
    ) -> List[NotificationResponse]:
        """
        Send notification based on event type
        Looks up template for event and sends to preferred channel
        """
        pass
    
    @abstractmethod
    def register_template(self, event_type: str, template: Dict[str, Any]) -> None:
        """Register notification template for event type"""
        pass
