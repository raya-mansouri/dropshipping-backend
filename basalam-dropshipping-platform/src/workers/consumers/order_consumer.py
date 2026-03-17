import json
import logging
from typing import Dict, Any

from aiokafka import AIOKafkaConsumer

logger = logging.getLogger(__name__)


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
                logger.error(f"Error processing order event: {e}")

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
            logger.warning(f"Unknown order event type: {event_type}")

    async def _handle_order_created(self, event: Dict[str, Any]):
        metadata = event.get("metadata", {})
        order_id = metadata.get("order_id")
        shop_id = metadata.get("shop_id")
        total_price = metadata.get("total_price")
        items_count = metadata.get("items_count")
        logger.info(
            f"Processing OrderCreated: order_id={order_id}, shop_id={shop_id}, "
            f"total_price={total_price}, items_count={items_count}"
        )

    async def _handle_order_paid(self, event: Dict[str, Any]):
        metadata = event.get("metadata", {})
        order_id = metadata.get("order_id")
        payment_id = metadata.get("payment_id")
        amount = metadata.get("amount")
        logger.info(
            f"Processing OrderPaid: order_id={order_id}, "
            f"payment_id={payment_id}, amount={amount}"
        )

    async def _handle_order_cancelled(self, event: Dict[str, Any]):
        metadata = event.get("metadata", {})
        order_id = metadata.get("order_id")
        reason = metadata.get("reason")
        refunded_amount = metadata.get("refunded_amount")
        logger.info(
            f"Processing OrderCancelled: order_id={order_id}, "
            f"reason={reason}, refunded_amount={refunded_amount}"
        )

    async def _handle_order_status_changed(self, event: Dict[str, Any]):
        metadata = event.get("metadata", {})
        order_id = metadata.get("order_id")
        old_status = metadata.get("old_status")
        new_status = metadata.get("new_status")
        actor = metadata.get("actor")
        logger.info(
            f"Processing OrderStatusChanged: order_id={order_id}, "
            f"old_status={old_status}, new_status={new_status}, actor={actor}"
        )

    async def _handle_order_shipped(self, event: Dict[str, Any]):
        metadata = event.get("metadata", {})
        order_id = metadata.get("order_id")
        shipment_id = metadata.get("shipment_id")
        tracking_code = metadata.get("tracking_code")
        carrier = metadata.get("carrier")
        logger.info(
            f"Processing OrderShipped: order_id={order_id}, shipment_id={shipment_id}, "
            f"tracking_code={tracking_code}, carrier={carrier}"
        )
