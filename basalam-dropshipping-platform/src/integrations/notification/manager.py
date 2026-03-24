"""
Notification Manager
===================
Manages all notification adapters and provides unified interface

This is the PORT IMPLEMENTATION that ties all adapters together.
"""
from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import UUID

from .ports import (
    NotificationPort,
    NotificationChannel,
    NotificationPriority,
    NotificationRequest,
    NotificationResponse,
    NotificationRecipient,
    NotificationContent,
)
from .adapters.sms import KavenegarSMSAdapter
from .adapters.in_app import InAppNotificationAdapter
from .adapters.webhook import WebhookNotificationAdapter


class NotificationManager:
    """
    Manages all notification channels
    
    Provides unified interface for sending notifications
    across multiple channels (SMS, In-App, Webhook)
    """
    
    def __init__(self):
        self._adapters: Dict[NotificationChannel, NotificationPort] = {}
        self._templates: Dict[str, Dict[str, Any]] = {}
        self._default_channel = NotificationChannel.IN_APP
        
        # Register default adapters
        self._register_default_adapters()
    
    def _register_default_adapters(self):
        """Register built-in adapters"""
        # These would be initialized with proper config
        # In production, load from config
        pass
    
    def register_adapter(self, channel: NotificationChannel, adapter: NotificationPort):
        """Register a notification adapter for a channel"""
        self._adapters[channel] = adapter
    
    def register_template(self, event_type: str, template: Dict[str, Any]):
        """Register notification template for event type"""
        self._templates[event_type] = template
    
    async def send(
        self,
        channel: NotificationChannel,
        recipient: NotificationRecipient,
        content: NotificationContent,
        priority: NotificationPriority = NotificationPriority.NORMAL
    ) -> NotificationResponse:
        """Send notification via specific channel"""
        adapter = self._adapters.get(channel)
        
        if not adapter:
            return NotificationResponse(
                success=False,
                error=f"No adapter registered for channel: {channel}",
                provider="manager"
            )
        
        request = NotificationRequest(
            channel=channel,
            recipient=recipient,
            content=content,
            priority=priority
        )
        
        return await adapter.send(request)
    
    async def send_multi_channel(
        self,
        channels: List[NotificationChannel],
        recipient: NotificationRecipient,
        content: NotificationContent,
        priority: NotificationPriority = NotificationPriority.NORMAL
    ) -> List[NotificationResponse]:
        """Send same notification to multiple channels"""
        responses = []
        
        for channel in channels:
            response = await self.send(channel, recipient, content, priority)
            responses.append(response)
        
        return responses
    
    async def notify_event(
        self,
        event_type: str,
        recipient: NotificationRecipient,
        event_data: Dict[str, Any],
        preferred_channels: Optional[List[NotificationChannel]] = None
    ) -> List[NotificationResponse]:
        """
        Send notification based on event type
        
        Looks up template for event and sends to preferred channels
        """
        template = self._templates.get(event_type, {})
        
        # Build content from template
        title = template.get("title", event_type).format(**event_data)
        body = template.get("body", "").format(**event_data)
        
        content = NotificationContent(
            title=title,
            body=body,
            template_id=event_type,
            variables=event_data,
            action_url=template.get("action_url", "").format(**event_data)
        )
        
        channels = preferred_channels or [self._default_channel]
        
        return await self.send_multi_channel(channels, recipient, content)
    
    async def notify_user(
        self,
        user_id: UUID,
        title: str,
        body: str,
        channels: Optional[List[NotificationChannel]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[NotificationResponse]:
        """Send notification to user via preferred channels"""
        recipient = NotificationRecipient(
            user_id=user_id,
            phone=metadata.get("phone") if metadata else None,
            webhook_url=metadata.get("webhook_url") if metadata else None
        )
        
        content = NotificationContent(
            title=title,
            body=body,
            variables=metadata or {}
        )
        
        channels = channels or [self._default_channel]
        
        return await self.send_multi_channel(channels, recipient, content)


# ============================================
# Factory Function for Easy Setup
# ============================================

def create_notification_manager(config: Dict[str, Any]) -> NotificationManager:
    """Create and configure notification manager"""
    manager = NotificationManager()
    
    # Register SMS adapter
    if config.get("sms"):
        sms_adapter = KavenegarSMSAdapter(
            api_key=config["sms"].get("api_key", ""),
            sender=config["sms"].get("sender", "10000000")
        )
        manager.register_adapter(NotificationChannel.SMS, sms_adapter)
    
    # Register In-App adapter
    inapp_adapter = InAppNotificationAdapter()
    manager.register_adapter(NotificationChannel.IN_APP, inapp_adapter)
    
    # Register Webhook adapter
    if config.get("webhook"):
        webhook_adapter = WebhookNotificationAdapter(
            secret_key=config["webhook"].get("secret_key", "")
        )
        manager.register_adapter(NotificationChannel.WEBHOOK, webhook_adapter)
    
    # Register templates
    manager.register_template("order_created", {
        "title": "New Order #{order_id}",
        "body": "You have a new order. Total: {total_price}",
        "action_url": "/orders/{order_id}"
    })
    
    manager.register_template("order_shipped", {
        "title": "Order Shipped #{order_id}",
        "body": "Your order has been shipped. Tracking: {tracking_code}",
        "action_url": "/orders/{order_id}"
    })
    
    manager.register_template("payment_received", {
        "title": "Payment Confirmed",
        "body": "Payment of {amount} received for order #{order_id}",
        "action_url": "/payments/{order_id}"
    })
    
    manager.register_template("inventory_low", {
        "title": "Low Inventory Alert",
        "body": "{product_name} inventory is low ({quantity} remaining)",
        "action_url": "/products/{product_id}"
    })
    
    return manager
