import json
import logging
from typing import Dict, Any
from uuid import UUID

from aiokafka import AIOKafkaConsumer

logger = logging.getLogger(__name__)


class ProductConsumer:
    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str = "product-consumer-group",
    ):
        self.bootstrap_servers = bootstrap_servers
        self.group_id = group_id
        self.consumer: AIOKafkaConsumer = None

    async def start(self):
        self.consumer = AIOKafkaConsumer(
            "product.updated",
            bootstrap_servers=self.bootstrap_servers,
            group_id=self.group_id,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            auto_offset_reset="earliest",
            enable_auto_commit=True,
        )
        await self.consumer.start()
        logger.info("Product consumer started")

    async def stop(self):
        if self.consumer:
            await self.consumer.stop()
            logger.info("Product consumer stopped")

    async def consume(self):
        async for message in self.consumer:
            try:
                event = message.value
                event_type = event.get("event_type")
                await self._handle_event(event_type, event)
            except Exception as e:
                logger.error(f"Error processing product event: {e}")

    async def _handle_event(self, event_type: str, event: Dict[str, Any]):
        handlers = {
            "ProductCreated": self._handle_product_created,
            "ProductUpdated": self._handle_product_updated,
            "ProductStatusChanged": self._handle_product_status_changed,
            "ProductDeleted": self._handle_product_deleted,
            "ProductSynced": self._handle_product_synced,
        }

        handler = handlers.get(event_type)
        if handler:
            await handler(event)
        else:
            logger.warning(f"Unknown product event type: {event_type}")

    async def _handle_product_created(self, event: Dict[str, Any]):
        product_id = event.get("metadata", {}).get("product_id")
        shop_id = event.get("metadata", {}).get("shop_id")
        title = event.get("metadata", {}).get("title")
        logger.info(
            f"Processing ProductCreated: product_id={product_id}, shop_id={shop_id}, title={title}"
        )

    async def _handle_product_updated(self, event: Dict[str, Any]):
        product_id = event.get("metadata", {}).get("product_id")
        changes = event.get("metadata", {}).get("changes", {})
        logger.info(
            f"Processing ProductUpdated: product_id={product_id}, changes={changes}"
        )

    async def _handle_product_status_changed(self, event: Dict[str, Any]):
        product_id = event.get("metadata", {}).get("product_id")
        old_status = event.get("metadata", {}).get("old_status")
        new_status = event.get("metadata", {}).get("new_status")
        logger.info(
            f"Processing ProductStatusChanged: product_id={product_id}, "
            f"old_status={old_status}, new_status={new_status}"
        )

    async def _handle_product_deleted(self, event: Dict[str, Any]):
        product_id = event.get("metadata", {}).get("product_id")
        logger.info(f"Processing ProductDeleted: product_id={product_id}")

    async def _handle_product_synced(self, event: Dict[str, Any]):
        product_id = event.get("metadata", {}).get("product_id")
        basalam_product_id = event.get("metadata", {}).get("basalam_product_id")
        logger.info(
            f"Processing ProductSynced: product_id={product_id}, "
            f"basalam_product_id={basalam_product_id}"
        )
