"""
Order Webhook Processor
=======================
Handles order.created and order.updated events from shop platforms.
"""

from typing import Dict, Any
import structlog

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base import WebhookProcessor
from src.core.repository.unit_of_work import UnitOfWork


logger = structlog.get_logger(__name__)


class OrderWebhookProcessor(WebhookProcessor):
    """
    Processes order-related webhook events.

    Handles:
    - order.created: New order received
    - order.updated: Order status changed
    """

    STATUS_MAP = {
        "pending": "pending",
        "processing": "processing",
        "shipped": "shipped",
        "delivered": "delivered",
        "cancelled": "cancelled",
        "refunded": "refunded",
    }

    def __init__(self, secret: str, db_session: AsyncSession):
        super().__init__(secret)
        self.db_session = db_session

    async def process(self, payload: Dict[str, Any], headers: Dict[str, str]) -> bool:
        """
        Process order webhook event.

        Expected payload structure:
        {
            "event_type": "order.created" | "order.updated",
            "data": {
                "order_id": "shop-order-123",
                "status": "processing",
                "customer": {...},
                "items": [...],
                "total_price": 150000
            }
        }
        """
        event_type = self.get_event_type(payload, headers)

        if event_type not in ("order.created", "order.updated"):
            logger.warning("unexpected_event_type", event_type=event_type)
            return False

        event_data = self.extract_event_data(payload)

        order_id = event_data.get("order_id")
        if not order_id:
            logger.error("Missing required field: order_id")
            return False

        try:
            await self._update_order_status(order_id, event_data)
            logger.info("processed_order_event", order_id=str(order_id), event_type=event_type)
            return True
        except Exception as e:
            logger.error("failed_to_process_order", error=str(e))
            return False

    async def _update_order_status(self, order_id: str, data: Dict[str, Any]) -> None:
        """Update order status in the database"""
        from src.domains.orders.models import Order

        async with UnitOfWork(self.db_session):
            stmt = select(Order).where(Order.external_order_id == order_id)
            result = await self.db_session.execute(stmt)
            order = result.scalar_one_or_none()

            if order:
                new_status = data.get("status", "").lower()
                mapped_status = self.STATUS_MAP.get(new_status, "pending")
                order.status = mapped_status

                if "total_price" in data:
                    order.total_price = data["total_price"]

                logger.info("updated_order_status", order_id=str(order_id), status=mapped_status)
            else:
                logger.warning("order_not_found", order_id=str(order_id))
