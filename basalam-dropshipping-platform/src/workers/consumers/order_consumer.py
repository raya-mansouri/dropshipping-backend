"""
Order Kafka Consumer
====================
Consumes order events and triggers business operations:
- Notifications to sellers/suppliers
- Audit trail recording
- Shipment tracking updates
"""
import json
import structlog
from datetime import datetime, timezone
from typing import Dict, Any
from uuid import uuid4

from aiokafka import AIOKafkaConsumer

from src.core.database import async_session_maker

logger = structlog.get_logger("workers.order_consumer")


class OrderConsumer:
    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str = "order-consumer-group",
    ):
        self.bootstrap_servers = bootstrap_servers
        self.group_id = group_id
        self.consumer: AIOKafkaConsumer = None

    async def start(self):
        self.consumer = AIOKafkaConsumer(
            "order.created",
            bootstrap_servers=self.bootstrap_servers,
            group_id=self.group_id,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            auto_offset_reset="earliest",
            enable_auto_commit=True,
        )
        await self.consumer.start()
        logger.info("Order consumer started")

    async def stop(self):
        if self.consumer:
            await self.consumer.stop()
            logger.info("Order consumer stopped")

    async def consume(self):
        async for message in self.consumer:
            try:
                event = message.value
                event_type = event.get("event_type")
                await self._handle_event(event_type, event)
            except Exception as e:
                logger.error("Error processing order event", error=str(e), exc_info=True)

    async def _handle_event(self, event_type: str, event: Dict[str, Any]):
        handlers = {
            "OrderCreated": self._handle_order_created,
            "OrderPaid": self._handle_order_paid,
            "OrderCancelled": self._handle_order_cancelled,
            "OrderStatusChanged": self._handle_order_status_changed,
            "OrderShipped": self._handle_order_shipped,
        }

        handler = handlers.get(event_type)
        if handler:
            await handler(event)
        else:
            logger.warning("Unknown order event type", event_type=event_type)

    async def _handle_order_created(self, event: Dict[str, Any]):
        metadata = event.get("metadata", {})
        order_id = metadata.get("order_id")
        shop_id = metadata.get("shop_id")
        total_price = metadata.get("total_price")
        items_count = metadata.get("items_count")

        if not order_id:
            logger.warning("OrderCreated event missing order_id")
            return

        logger.info(
            "Processing OrderCreated",
            order_id=str(order_id),
            shop_id=str(shop_id),
            total_price=total_price,
            items_count=items_count,
        )

        async with async_session_maker() as session:
            try:
                from src.integrations.notification.manager import create_notification_manager
                from src.integrations.notification.ports import (
                    NotificationChannel,
                    NotificationRecipient,
                    NotificationContent,
                )

                notification_mgr = create_notification_manager({})

                if shop_id:
                    from src.domains.shops.models import Shop
                    from sqlalchemy import select

                    shop_result = await session.execute(
                        select(Shop).where(Shop.id == shop_id)
                    )
                    shop = shop_result.scalar_one_or_none()

                    if shop:
                        recipient = NotificationRecipient(user_id=shop.account_id)
                        content = NotificationContent(
                            title=f"New Order #{order_id}",
                            body=f"You have a new order with {items_count or 0} item(s). Total: {total_price}",
                            template_id="order_created",
                            variables={
                                "order_id": str(order_id),
                                "total_price": str(total_price),
                                "items_count": items_count,
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
                    "Failed to send OrderCreated notification",
                    order_id=str(order_id),
                    error=str(e),
                )

    async def _handle_order_paid(self, event: Dict[str, Any]):
        metadata = event.get("metadata", {})
        order_id = metadata.get("order_id")
        payment_id = metadata.get("payment_id")
        amount = metadata.get("amount")

        if not order_id:
            logger.warning("OrderPaid event missing order_id")
            return

        logger.info(
            "Processing OrderPaid",
            order_id=str(order_id),
            payment_id=str(payment_id),
            amount=amount,
        )

        async with async_session_maker() as session:
            try:
                from src.integrations.notification.manager import create_notification_manager
                from src.integrations.notification.ports import (
                    NotificationChannel,
                    NotificationRecipient,
                    NotificationContent,
                )
                from src.domains.orders.models import Order, OrderItem
                from src.domains.shops.models import Shop
                from sqlalchemy import select

                notification_mgr = create_notification_manager({})

                # Fetch order to get seller shop_id
                order_result = await session.execute(
                    select(Order).where(Order.id == order_id)
                )
                order = order_result.scalar_one_or_none()

                if order:
                    # Notify seller
                    shop_result = await session.execute(
                        select(Shop).where(Shop.id == order.shop_id)
                    )
                    seller_shop = shop_result.scalar_one_or_none()
                    if seller_shop:
                        recipient = NotificationRecipient(user_id=seller_shop.account_id)
                        content = NotificationContent(
                            title=f"Payment Confirmed for Order #{order_id}",
                            body=f"Payment of {amount} received for order #{order_id}.",
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

                    # Notify each distinct supplier — batch load all supplier shops
                    items_result = await session.execute(
                        select(OrderItem).where(OrderItem.order_id == order_id)
                    )
                    items = items_result.scalars().all()
                    supplier_ids = {item.supplier_shop_id for item in items}

                    # Single query instead of N queries (fixes N+1)
                    if supplier_ids:
                        shops_result = await session.execute(
                            select(Shop).where(Shop.id.in_(supplier_ids))
                        )
                        shop_by_id = {s.id: s for s in shops_result.scalars().all()}
                    else:
                        shop_by_id = {}

                    for supplier_id in supplier_ids:
                        supplier_shop = shop_by_id.get(supplier_id)
                        if supplier_shop:
                            supplier_items = [
                                i for i in items if i.supplier_shop_id == supplier_id
                            ]
                            recipient = NotificationRecipient(user_id=supplier_shop.account_id)
                            content = NotificationContent(
                                title=f"New Order to Fulfill #{order_id}",
                                body=(
                                    f"Order #{order_id} has been paid. "
                                    f"You have {len(supplier_items)} item(s) to ship."
                                ),
                                template_id="order_paid",
                                variables={
                                    "order_id": str(order_id),
                                    "item_count": len(supplier_items),
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
                    "Failed to process OrderPaid notifications",
                    order_id=str(order_id),
                    error=str(e),
                )

    async def _handle_order_cancelled(self, event: Dict[str, Any]):
        metadata = event.get("metadata", {})
        order_id = metadata.get("order_id")
        reason = metadata.get("reason")
        refunded_amount = metadata.get("refunded_amount")

        if not order_id:
            logger.warning("OrderCancelled event missing order_id")
            return

        logger.info(
            "Processing OrderCancelled",
            order_id=str(order_id),
            reason=reason,
            refunded_amount=refunded_amount,
        )

        async with async_session_maker() as session:
            try:
                from src.integrations.notification.manager import create_notification_manager
                from src.integrations.notification.ports import (
                    NotificationChannel,
                    NotificationRecipient,
                    NotificationContent,
                )
                from src.domains.orders.models import Order
                from src.domains.shops.models import Shop
                from sqlalchemy import select

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
                            title=f"Order Cancelled #{order_id}",
                            body=(
                                f"Order #{order_id} has been cancelled. "
                                f"Reason: {reason or 'N/A'}. "
                                f"Refunded amount: {refunded_amount or 'N/A'}"
                            ),
                            template_id="order_cancelled",
                            variables={
                                "order_id": str(order_id),
                                "reason": reason or "N/A",
                                "refunded_amount": str(refunded_amount or "N/A"),
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
                    "Failed to process OrderCancelled notification",
                    order_id=str(order_id),
                    error=str(e),
                )

    async def _handle_order_status_changed(self, event: Dict[str, Any]):
        metadata = event.get("metadata", {})
        order_id = metadata.get("order_id")
        old_status = metadata.get("old_status")
        new_status = metadata.get("new_status")
        actor = metadata.get("actor")

        if not order_id:
            logger.warning("OrderStatusChanged event missing order_id")
            return

        logger.info(
            "Processing OrderStatusChanged",
            order_id=str(order_id),
            old_status=old_status,
            new_status=new_status,
            actor=actor,
        )

        async with async_session_maker() as session:
            try:
                from src.domains.orders.repository import OrderHistoryRepository

                history_repo = OrderHistoryRepository(session)

                reason = metadata.get("reason")
                history_data = {
                    "id": uuid4(),
                    "order_id": order_id,
                    "from_status": old_status,
                    "to_status": new_status,
                    "actor_type": actor or "system",
                    "reason": reason or f"Status changed from {old_status} to {new_status}",
                    "extra_data": metadata,
                    "created_at": datetime.now(timezone.utc),
                }
                await history_repo.create(history_data)
                await session.commit()

                logger.info(
                    "Recorded order status change in audit trail",
                    order_id=str(order_id),
                    old_status=old_status,
                    new_status=new_status,
                )
            except Exception as e:
                logger.error(
                    "Failed to record OrderStatusChanged audit",
                    order_id=str(order_id),
                    error=str(e),
                )

    async def _handle_order_shipped(self, event: Dict[str, Any]):
        metadata = event.get("metadata", {})
        order_id = metadata.get("order_id")
        shipment_id = metadata.get("shipment_id")
        tracking_code = metadata.get("tracking_code")
        carrier = metadata.get("carrier")

        if not order_id:
            logger.warning("OrderShipped event missing order_id")
            return

        logger.info(
            "Processing OrderShipped",
            order_id=str(order_id),
            shipment_id=str(shipment_id),
            tracking_code=tracking_code,
            carrier=carrier,
        )

        async with async_session_maker() as session:
            try:
                from src.integrations.notification.manager import create_notification_manager
                from src.integrations.notification.ports import (
                    NotificationChannel,
                    NotificationRecipient,
                    NotificationContent,
                )
                from src.domains.orders.models import Order
                from src.domains.shops.models import Shop
                from sqlalchemy import select

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
                        tracking_info = (
                            f"Tracking code: {tracking_code}, Carrier: {carrier}"
                            if tracking_code
                            else "No tracking info yet"
                        )
                        recipient = NotificationRecipient(user_id=shop.account_id)
                        content = NotificationContent(
                            title=f"Order Shipped #{order_id}",
                            body=f"Your order #{order_id} has been shipped. {tracking_info}",
                            template_id="order_shipped",
                            variables={
                                "order_id": str(order_id),
                                "tracking_code": tracking_code or "N/A",
                                "carrier": carrier or "N/A",
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
                    "Failed to process OrderShipped notification",
                    order_id=str(order_id),
                    error=str(e),
                )
