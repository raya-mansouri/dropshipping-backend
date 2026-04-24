"""
Inventory Webhook Processor
===========================
Handles inventory.updated events from supplier platforms.
"""

from typing import Dict, Any
import structlog

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base import WebhookProcessor
from src.core.repository.unit_of_work import UnitOfWork


logger = structlog.get_logger(__name__)


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
            logger.warning("unexpected_event_type", event_type=event_type)
            return False

        event_data = self.extract_event_data(payload)

        variant_id = event_data.get("variant_id")
        inventory = event_data.get("inventory")

        if not variant_id or inventory is None:
            logger.error("Missing required fields: variant_id or inventory")
            return False

        try:
            await self._update_inventory(variant_id, inventory)
            logger.info("updated_inventory", variant_id=str(variant_id), inventory=inventory)
            return True
        except Exception as e:
            logger.error("failed_to_update_inventory", error=str(e))
            return False

    async def _update_inventory(self, variant_id: str, inventory: int) -> None:
        """
        Update the inventory for a SupplierVariant.

        Args:
            variant_id: The supplier variant ID
            inventory: New inventory quantity
        """
        from src.domains.products.models import SupplierVariant, ProductVariant

        async with UnitOfWork(self.db_session):
            stmt = select(SupplierVariant).join(
                ProductVariant, SupplierVariant.variant_id == ProductVariant.id
            ).where(
                ProductVariant.external_variant_id == variant_id
            )
            result = await self.db_session.execute(stmt)
            variant = result.scalar_one_or_none()

            if variant:
                variant.inventory = inventory
                logger.info("updated_inventory", variant_id=str(variant_id), inventory=inventory)
            else:
                logger.warning("variant_not_found", variant_id=str(variant_id))
