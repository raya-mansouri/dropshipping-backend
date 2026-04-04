"""
Payment Updated Kafka Consumer
==============================
Consumes payment.updated events and processes escrow/payout transitions.
"""
import asyncio
import json
import logging
from typing import Dict, Any

from aiokafka import AIOKafkaConsumer

from src.core.config import get_settings

logger = logging.getLogger(__name__)


class PaymentUpdatedConsumer:
    """Consumes payment.updated Kafka topic."""

    def __init__(self):
        self.settings = get_settings()
        self.consumer: AIOKafkaConsumer = None

    async def start(self):
        self.consumer = AIOKafkaConsumer(
            "payment.updated",
            bootstrap_servers=self.settings.kafka_bootstrap_servers,
            group_id="payment-processor",
            auto_offset_reset="latest",
            enable_auto_commit=False,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        )
        await self.consumer.start()
        logger.info("PaymentUpdatedConsumer started")

    async def stop(self):
        if self.consumer:
            await self.consumer.stop()
            logger.info("PaymentUpdatedConsumer stopped")

    async def process_messages(self):
        """Process payment.updated events."""
        from src.core.database import async_session_maker
        from src.domains.payments.service import PaymentService

        async for message in self.consumer:
            try:
                event = message.value
                event_type = event.get("event_type")
                payment_id = event.get("payment_id")
                data = event.get("data", {})

                logger.info(f"Processing payment event: {event_type} for payment {payment_id}")

                async with async_session_maker() as session:
                    payment_service = PaymentService(session)

                    if event_type == "payment.captured":
                        gateway_txn_id = data.get("gateway_transaction_id")
                        if gateway_txn_id:
                            await payment_service.mark_seller_paid(
                                payment_id=payment_id,
                                gateway_transaction_id=gateway_txn_id,
                            )

                    elif event_type == "delivery.confirmed":
                        order_item_id = data.get("order_item_id")
                        confirmed_by = data.get("confirmed_by", "auto")
                        if order_item_id:
                            await payment_service.create_payout_after_delivery(
                                order_item_id=order_item_id,
                                delivery_confirmed_by=confirmed_by,
                            )

                    await session.commit()

                await self.consumer.commit()
                logger.info(f"Processed payment event {event_type} for {payment_id}")

            except Exception as e:
                logger.error(f"Failed to process payment event: {e}")
                # Don't commit - will retry


async def run_payment_consumer():
    """Entry point for running payment consumer."""
    consumer = PaymentUpdatedConsumer()
    await consumer.start()
    try:
        await consumer.process_messages()
    finally:
        await consumer.stop()


if __name__ == "__main__":
    asyncio.run(run_payment_consumer())
