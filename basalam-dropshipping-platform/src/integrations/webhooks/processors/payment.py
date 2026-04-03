"""
Payment Webhook Processor
=========================
Handles payment.completed and payment.failed events.
"""

from typing import Dict, Any
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base import WebhookProcessor
from src.core.repository.unit_of_work import UnitOfWork


logger = logging.getLogger(__name__)


class PaymentWebhookProcessor(WebhookProcessor):
    """
    Processes payment-related webhook events.

    Handles:
    - payment.completed: Payment was successful
    - payment.failed: Payment failed
    """

    def __init__(self, secret: str, db_session: AsyncSession):
        super().__init__(secret)
        self.db_session = db_session

    async def process(self, payload: Dict[str, Any], headers: Dict[str, str]) -> bool:
        """
        Process payment webhook event.

        Expected payload structure:
        {
            "event_type": "payment.completed" | "payment.failed",
            "data": {
                "payment_id": "payment-123",
                "order_id": "order-456",
                "amount": 99.99,
                "currency": "USD",
                "status": "completed" | "failed",
                "transaction_id": "txn-789"
            }
        }
        """
        event_type = self.get_event_type(payload, headers)

        if event_type not in ("payment.completed", "payment.failed"):
            logger.warning(f"Unexpected event type: {event_type}")
            return False

        event_data = self.extract_event_data(payload)

        payment_id = event_data.get("payment_id")
        order_id = event_data.get("order_id")

        if not payment_id and not order_id:
            logger.error("Missing required fields: payment_id or order_id")
            return False

        try:
            if event_type == "payment.completed":
                await self._handle_payment_completed(event_data)
            else:
                await self._handle_payment_failed(event_data)

            logger.info(f"Processed payment event: {event_type}")
            return True
        except Exception as e:
            logger.error(f"Failed to process payment: {e}")
            return False

    async def _handle_payment_completed(self, data: Dict[str, Any]) -> None:
        """Handle successful payment"""
        from src.domains.orders.models import Order

        order_id = data.get("order_id")
        if not order_id:
            return

        async with UnitOfWork(self.db_session):
            stmt = select(Order).where(Order.external_order_id == order_id)
            result = await self.db_session.execute(stmt)
            order = result.scalar_one_or_none()

            if order:
                order.payment_status = "paid"
                logger.info(f"Marked order {order_id} as paid")

    async def _handle_payment_failed(self, data: Dict[str, Any]) -> None:
        """Handle failed payment"""
        from src.domains.orders.models import Order

        order_id = data.get("order_id")
        if not order_id:
            return

        async with UnitOfWork(self.db_session):
            stmt = select(Order).where(Order.external_order_id == order_id)
            result = await self.db_session.execute(stmt)
            order = result.scalar_one_or_none()

            if order:
                order.payment_status = "failed"
                logger.info(f"Marked order {order_id} as payment failed")
