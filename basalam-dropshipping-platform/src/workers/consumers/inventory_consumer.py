import json
import logging
from typing import Dict, Any

from aiokafka import AIOKafkaConsumer

logger = logging.getLogger(__name__)


class InventoryConsumer:
    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str = "inventory-consumer-group",
    ):
        self.bootstrap_servers = bootstrap_servers
        self.group_id = group_id
        self.consumer: AIOKafkaConsumer = None

    async def start(self):
        self.consumer = AIOKafkaConsumer(
            "inventory.updated",
            bootstrap_servers=self.bootstrap_servers,
            group_id=self.group_id,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            auto_offset_reset="earliest",
            enable_auto_commit=True,
        )
        await self.consumer.start()
        logger.info("Inventory consumer started")

    async def stop(self):
        if self.consumer:
            await self.consumer.stop()
            logger.info("Inventory consumer stopped")

    async def consume(self):
        async for message in self.consumer:
            try:
                event = message.value
                event_type = event.get("event_type")
                await self._handle_event(event_type, event)
            except Exception as e:
                logger.error(f"Error processing inventory event: {e}")

    async def _handle_event(self, event_type: str, event: Dict[str, Any]):
        handlers = {
            "InventoryUpdated": self._handle_inventory_updated,
            "InventoryReserved": self._handle_inventory_reserved,
            "InventoryReleased": self._handle_inventory_released,
            "InventorySyncCompleted": self._handle_inventory_sync_completed,
        }

        handler = handlers.get(event_type)
        if handler:
            await handler(event)
        else:
            logger.warning(f"Unknown inventory event type: {event_type}")

    async def _handle_inventory_updated(self, event: Dict[str, Any]):
        metadata = event.get("metadata", {})
        variant_id = metadata.get("variant_id")
        old_quantity = metadata.get("old_quantity")
        new_quantity = metadata.get("new_quantity")
        source = metadata.get("source")
        logger.info(
            f"Processing InventoryUpdated: variant_id={variant_id}, "
            f"old_quantity={old_quantity}, new_quantity={new_quantity}, source={source}"
        )

    async def _handle_inventory_reserved(self, event: Dict[str, Any]):
        metadata = event.get("metadata", {})
        variant_id = metadata.get("variant_id")
        order_item_id = metadata.get("order_item_id")
        quantity = metadata.get("quantity")
        expires_at = metadata.get("expires_at")
        logger.info(
            f"Processing InventoryReserved: variant_id={variant_id}, "
            f"order_item_id={order_item_id}, quantity={quantity}, expires_at={expires_at}"
        )

    async def _handle_inventory_released(self, event: Dict[str, Any]):
        metadata = event.get("metadata", {})
        variant_id = metadata.get("variant_id")
        order_item_id = metadata.get("order_item_id")
        quantity = metadata.get("quantity")
        reason = metadata.get("reason")
        logger.info(
            f"Processing InventoryReleased: variant_id={variant_id}, "
            f"order_item_id={order_item_id}, quantity={quantity}, reason={reason}"
        )

    async def _handle_inventory_sync_completed(self, event: Dict[str, Any]):
        metadata = event.get("metadata", {})
        integration_id = metadata.get("integration_id")
        variants_synced = metadata.get("variants_synced")
        errors = metadata.get("errors", [])
        logger.info(
            f"Processing InventorySyncCompleted: integration_id={integration_id}, "
            f"variants_synced={variants_synced}, errors_count={len(errors)}"
        )
