"""
Inventory Webhook Processor
===========================
Handles inventory.updated events from supplier platforms.
"""

from typing import Dict, Any
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base import WebhookProcessor


logger = logging.getLogger(__name__)


class InventoryWebhookProcessor(WebhookProcessor):
    """
    Processes inventory-related webhook events.

    Handles:
    - inventory.updated: Update SupplierVariant inventory levels
    """

    def __init__(self, secret: str, db_session: AsyncSession):
        super().__init__(secret)
        self.db_session = db_session

    async def process(self, payload: Dict[str, Any], headers: Dict[str, str]) -> bool:
        """
        Process inventory update webhook.

        Expected payload structure:
        {
            "event_type": "inventory.updated",
            "data": {
                "variant_id": "supplier-variant-123",
                "inventory": 100,
                "platform_id": "supplier-platform-1"
            }
        }
        """
        event_type = self.get_event_type(payload, headers)

        if event_type != "inventory.updated":
            logger.warning(f"Unexpected event type: {event_type}")
            return False

        event_data = self.extract_event_data(payload)

        variant_id = event_data.get("variant_id")
        inventory = event_data.get("inventory")

        if not variant_id or inventory is None:
            logger.error("Missing required fields: variant_id or inventory")
            return False

        try:
            await self._update_inventory(variant_id, inventory)
            logger.info(f"Updated inventory for variant {variant_id}: {inventory}")
            return True
        except Exception as e:
            logger.error(f"Failed to update inventory: {e}")
            return False

    async def _update_inventory(self, variant_id: str, inventory: int) -> None:
        """
        Update the inventory for a SupplierVariant.

        Args:
            variant_id: The supplier variant ID
            inventory: New inventory quantity
        """
        from src.domains.suppliers.models import SupplierVariant

        stmt = select(SupplierVariant).where(
            SupplierVariant.external_variant_id == variant_id
        )
        result = await self.db_session.execute(stmt)
        variant = result.scalar_one_or_none()

        if variant:
            variant.inventory_quantity = inventory
            await self.db_session.commit()
        else:
            logger.warning(f"Variant not found: {variant_id}")
