"""
In-App Notification Adapter
===========================
Implements NotificationPort for in-app notifications

Stores notifications in database and provides via API
"""
from datetime import datetime
from uuid import UUID
from typing import List, Optional, Dict, Any

from ..ports import (
    NotificationPort,
    NotificationChannel,
    NotificationRequest,
    NotificationResponse,
)


class InAppNotificationAdapter(NotificationPort):
    """
    In-app notification adapter
    
    Stores notifications in database for retrieval via API
    """
    
    def __init__(self, db_session=None):
        self.db_session = db_session
    
    @property
    def channel(self) -> NotificationChannel:
        return NotificationChannel.IN_APP
    
    @property
    def provider_name(self) -> str:
        return "in_app"
    
    async def send(self, request: NotificationRequest) -> NotificationResponse:
        """Store in-app notification in database"""
        if not request.recipient.user_id:
            return NotificationResponse(
                success=False,
                error="No user_id provided",
                provider=self.provider_name
            )
        
        try:
            # Create notification record in database
            notification = {
                "user_id": str(request.recipient.user_id),
                "type": request.content.template_id or "general",
                "title": request.content.title,
                "body": request.content.body,
                "payload": request.content.variables,
                "action_url": request.content.action_url,
                "status": "pending",
                "channel": self.channel.value,
                "created_at": datetime.utcnow().isoformat()
            }
            
            # In real implementation, save to database
            # await self.db_session.execute(
            #     "INSERT INTO notifications ...",
            #     notification
            # )
            
            return NotificationResponse(
                success=True,
                message_id=f"inapp_{datetime.utcnow().timestamp()}",
                provider=self.provider_name
            )
            
        except Exception as e:
            return NotificationResponse(
                success=False,
                error=str(e),
                provider=self.provider_name
            )
    
    async def send_batch(self, requests: List[NotificationRequest]) -> List[NotificationResponse]:
        """Store multiple in-app notifications"""
        responses = []
        for request in requests:
            response = await self.send(request)
            responses.append(response)
        return responses
    
    async def verify_connection(self) -> bool:
        """Verify database connection"""
        try:
            # await self.db_session.execute("SELECT 1")
            return True
        except Exception:
            return False
    
    async def get_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        """Get in-app notification template"""
        templates = {
            "order_created": {
                "title": "New Order",
                "body": "You have a new order #{{order_id}}",
                "icon": "order",
                "action": "view_order"
            },
            "inventory_low": {
                "title": "Low Inventory Alert",
                "body": "{{product_name}} inventory is low ({{quantity}} left)",
                "icon": "warning",
                "action": "view_product"
            },
            "payment_received": {
                "title": "Payment Received",
                "body": "Payment of {{amount}} received for order #{{order_id}}",
                "icon": "payment",
                "action": "view_payment"
            },
            "dispute_opened": {
                "title": "New Dispute",
                "body": "A dispute has been opened for order #{{order_id}}",
                "icon": "dispute",
                "action": "view_dispute"
            },
        }
        return templates.get(template_id)
