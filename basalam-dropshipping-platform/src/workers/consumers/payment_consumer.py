"""
Payment Updated Kafka Consumer
==============================
Consumes payment.updated events and processes escrow/payout transitions.

Handles:
- payment.captured: Mark seller paid and enter escrow
- delivery.confirmed: Create supplier payout after delivery
- payment.held: Log escrow start, notify seller
- payment.released: Notify supplier about payout
- payment.refunded: Notify seller about refund
"""
import asyncio
import json
import structlog
from typing import Dict, Any

from aiokafka import AIOKafkaConsumer

from src.core.config import get_settings
from src.core.database import async_session_maker
from src.integrations.notification.manager import create_notification_manager
from src.integrations.notification.ports import (
    NotificationChannel,
    NotificationRecipient,
    NotificationContent,
)
from src.domains.payments.service import PaymentService
from src.domains.orders.models import Order, OrderItem
from src.domains.shops.models import Shop
from src.domains.shipping import ShippingService
from sqlalchemy import select

logger = structlog.get_logger("workers.payment_consumer")


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
        async for message in self.consumer:
            try:
                event = message.value
                event_type = event.get("event_type")
                payment_id = event.get("payment_id")
                data = event.get("data", {})

                logger.info(
                    "Processing payment event",
                    event_type=event_type,
                    payment_id=str(payment_id),
                )

                async with async_session_maker() as session:
                    try:
                        payment_service = PaymentService(session)

                        if event_type == "payment.captured":
                            await self._handle_payment_captured(
                                payment_service, payment_id, data
                            )

                        elif event_type == "delivery.confirmed":
                            await self._handle_delivery_confirmed(
                                payment_service, data
                            )

                        elif event_type == "payment.held":
                            await self._handle_payment_held(payment_id, data)

                        elif event_type == "payment.released":
                            await self._handle_payment_released(payment_id, data)

                        elif event_type == "payment.refunded":
                            await self._handle_payment_refunded(payment_id, data)

                        else:
                            logger.warning(
                                "Unknown payment event type",
                                event_type=event_type,
                                payment_id=str(payment_id),
                            )

                        await session.commit()
                    except Exception as inner_e:
                        await session.rollback()
                        raise inner_e

                await self.consumer.commit()
                logger.info(
                    "Processed payment event",
                    event_type=event_type,
                    payment_id=str(payment_id),
                )

            except Exception as e:
                logger.error(
                    "Failed to process payment event",
                    error=str(e),
                    exc_info=True,
                )
                # Don't commit - will retry

    async def _handle_payment_captured(
        self, payment_service, payment_id, data: Dict[str, Any]
    ):
        """Mark payment as seller-paid, enter escrow, and create shipment."""
        gateway_txn_id = data.get("gateway_transaction_id")
        order_id = data.get("order_id")

        if gateway_txn_id:
            await payment_service.mark_seller_paid(
                payment_id=payment_id,
                gateway_transaction_id=gateway_txn_id,
            )
            logger.info(
                "Payment captured and moved to escrow",
                payment_id=str(payment_id),
                gateway_txn_id=gateway_txn_id,
            )

        # Create shipment records for each order item after payment captured
        if order_id:
            try:
                from src.core.database import async_session_maker as asm

                async with asm() as ship_session:
                    shipping_service = ShippingService(ship_session)
                    order_result = await ship_session.execute(
                        select(Order).where(Order.id == order_id)
                    )
                    order = order_result.scalar_one_or_none()
                    if order:
                        order_items = order.items if hasattr(order, "items") else []
                        for item in order_items:
                            await shipping_service.create_shipment(
                                order_id=order_id,
                                order_item_id=item.id,
                            )
                    await ship_session.commit()
                    logger.info(
                        "Shipments created after payment capture",
                        order_id=str(order_id),
                    )
            except Exception as ship_err:
                logger.error(
                    "Failed to create shipments after payment capture",
                    order_id=str(order_id),
                    error=str(ship_err),
                )

    async def _handle_delivery_confirmed(
        self, payment_service, data: Dict[str, Any]
    ):
        """Create supplier payout after delivery confirmation."""
        order_item_id = data.get("order_item_id")
        confirmed_by = data.get("confirmed_by", "auto")
        if order_item_id:
            payout = await payment_service.create_payout_after_delivery(
                order_item_id=order_item_id,
                delivery_confirmed_by=confirmed_by,
            )
            if payout:
                logger.info(
                    "Created supplier payout after delivery",
                    order_item_id=str(order_item_id),
                    payout_id=str(payout.id),
                    amount=str(payout.amount),
                )

    async def _handle_payment_held(self, payment_id, data: Dict[str, Any]):
        """Log escrow start and notify seller."""
        order_id = data.get("order_id")
        amount = data.get("amount")
        gateway = data.get("gateway", "unknown")

        logger.info(
            "Payment held in escrow",
            payment_id=str(payment_id),
            order_id=str(order_id),
            amount=amount,
            gateway=gateway,
        )

        # Notify seller that payment is being held in escrow
        if order_id:
            async with async_session_maker() as session:
                try:
                    notification_mgr = create_notification_manager({})

                    order_result = await session.execute(
                        select(Order).where(Order.id == order_id)
                    )
                    order = order_result.scalar_one_or_none()
                    if order:
                        shop_result = await session.execute(
                            select(Shop).where(Shop.id == order.shop_id)
                        )
                        shop = shop_result.scalar_one_or_none()
                        if shop:
                            recipient = NotificationRecipient(user_id=shop.account_id)
                            content = NotificationContent(
                                title=f"Payment Confirmed for Order #{order_id}",
                                body=(
                                    f"Payment of {amount} has been received for order #{order_id} "
                                    f"and is being held in escrow."
                                ),
                                template_id="payment_received",
                                variables={
                                    "order_id": str(order_id),
                                    "amount": str(amount),
                                    "payment_id": str(payment_id),
                                },
                                action_url=f"/orders/{order_id}",
                            )
                            await notification_mgr.send(
                                channel=NotificationChannel.IN_APP,
                                recipient=recipient,
                                content=content,
                            )

                    await session.commit()
                except Exception as e:
                    logger.error(
                        "Failed to send payment held notification",
                        payment_id=str(payment_id),
                        error=str(e),
                    )

    async def _handle_payment_released(self, payment_id, data: Dict[str, Any]):
        """Notify supplier about payout."""
        supplier_id = data.get("supplier_id")
        amount = data.get("amount")
        payout_id = data.get("payout_id")

        logger.info(
            "Payment released to supplier",
            payment_id=str(payment_id),
            supplier_id=str(supplier_id),
            amount=amount,
            payout_id=str(payout_id),
        )

        if supplier_id:
            async with async_session_maker() as session:
                try:
                    notification_mgr = create_notification_manager({})

                    shop_result = await session.execute(
                        select(Shop).where(Shop.id == supplier_id)
                    )
                    shop = shop_result.scalar_one_or_none()
                    if shop:
                        recipient = NotificationRecipient(user_id=shop.account_id)
                        content = NotificationContent(
                            title="Payout Processed",
                            body=f"A payout of {amount} has been processed for your account.",
                            template_id="supplier_payout",
                            variables={
                                "amount": str(amount),
                                "payout_id": str(payout_id or ""),
                                "payment_id": str(payment_id),
                            },
                            action_url=f"/payouts/{payout_id}" if payout_id else "/payouts",
                        )
                        await notification_mgr.send(
                            channel=NotificationChannel.IN_APP,
                            recipient=recipient,
                            content=content,
                        )

                    await session.commit()
                except Exception as e:
                    logger.error(
                        "Failed to send payment released notification",
                        payment_id=str(payment_id),
                        error=str(e),
                    )

    async def _handle_payment_refunded(self, payment_id, data: Dict[str, Any]):
        """Notify seller about refund."""
        order_id = data.get("order_id")
        order_item_id = data.get("order_item_id")
        amount = data.get("amount")
        reason = data.get("reason")

        logger.info(
            "Payment refunded",
            payment_id=str(payment_id),
            order_id=str(order_id),
            order_item_id=str(order_item_id),
            amount=amount,
            reason=reason,
        )

        if order_id:
            async with async_session_maker() as session:
                try:
                    notification_mgr = create_notification_manager({})

                    order_result = await session.execute(
                        select(Order).where(Order.id == order_id)
                    )
                    order = order_result.scalar_one_or_none()
                    if order:
                        shop_result = await session.execute(
                            select(Shop).where(Shop.id == order.shop_id)
                        )
                        shop = shop_result.scalar_one_or_none()
                        if shop:
                            recipient = NotificationRecipient(user_id=shop.account_id)
                            content = NotificationContent(
                                title=f"Refund Processed for Order #{order_id}",
                                body=(
                                    f"Refund of {amount} for order #{order_id} has been processed."
                                    + (f" Reason: {reason}" if reason else "")
                                ),
                                template_id="refund_processed",
                                variables={
                                    "order_id": str(order_id),
                                    "amount": str(amount),
                                    "payment_id": str(payment_id),
                                    "reason": reason or "",
                                },
                                action_url=f"/orders/{order_id}",
                            )
                            await notification_mgr.send(
                                channel=NotificationChannel.IN_APP,
                                recipient=recipient,
                                content=content,
                            )

                    await session.commit()
                except Exception as e:
                    logger.error(
                        "Failed to send refund notification",
                        payment_id=str(payment_id),
                        error=str(e),
                    )


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
