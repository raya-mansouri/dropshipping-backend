"""
Product Webhook Processor
=========================
Handles product webhook events from Basalam platform.

Basalam sends webhooks with numeric event_id:
- event_id 8 = PRODUCT_CREATE_CHANGES (product created/modified)
- event_id 5 = VENDOR_NEW_ORDER
- event_id 7 = VENDOR_PARCEL_CHANGES

Webhook signature is in X-Basalam-Signature header.
"""

from typing import Dict, Any
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base import WebhookProcessor
from src.core.repository.unit_of_work import UnitOfWork


logger = logging.getLogger(__name__)


class ProductWebhookProcessor(WebhookProcessor):
    """
    Processes product-related webhook events from Basalam.

    Handles:
    - event_id 8 (PRODUCT_CREATE_CHANGES): Create or update SupplierProduct
    """

    # Basalam numeric event IDs
    EVENT_PRODUCT_CHANGES = 8

    def __init__(self, secret: str, db_session: AsyncSession):
        super().__init__(secret)
        self.db_session = db_session

    async def process(self, payload: Dict[str, Any], headers: Dict[str, str]) -> bool:
        """
        Process product webhook event from Basalam.

        Expected payload structure:
        {
            "event_id": 8,
            "data": {
                "id": 123,
                "title": "Product Name",
                "description": "...",
                "photo": {"original": "url", "id": 456},
                "status": {"value": 2976, "name": "active"},
                "price": 50000,
                "inventory": 10,
                "is_wholesale": false,
                ...
            }
        }
        """
        event_id = payload.get("event_id")

        if event_id != self.EVENT_PRODUCT_CHANGES:
            logger.warning(
                f"Unexpected event_id: {event_id}, "
                f"expected {self.EVENT_PRODUCT_CHANGES}"
            )
            return False

        event_data = self.extract_event_data(payload)

        product_id = event_data.get("id") or event_data.get("product_id")
        if not product_id:
            logger.error("Missing required field: id or product_id")
            return False

        try:
            async with UnitOfWork(self.db_session):
                existing = await self._find_product(str(product_id))
                if existing:
                    await self._update_product(str(product_id), event_data)
                    logger.info(f"Updated product from webhook: {product_id}")
                else:
                    await self._create_product(str(product_id), event_data)
                    logger.info(f"Created product from webhook: {product_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to process product webhook: {e}")
            return False

    async def _find_product(self, external_product_id: str):
        """Find existing product by external ID."""
        from src.domains.products.models import SupplierProduct

        stmt = select(SupplierProduct).where(
            SupplierProduct.external_product_id == external_product_id
        )
        result = await self.db_session.execute(stmt)
        return result.scalar_one_or_none()

    async def _create_product(self, product_id: str, data: Dict[str, Any]) -> None:
        """Create a new SupplierProduct from real Basalam webhook payload."""
        from src.domains.products.models import SupplierProduct

        # Map status from real Basalam shape
        status = self._map_status(data)

        product = SupplierProduct(
            external_product_id=product_id,
            title=data.get("title", ""),
            description=data.get("description", ""),
            status=status,
            has_variants=bool(data.get("variants")),
            raw_payload=data,
        )
        self.db_session.add(product)

    async def _update_product(self, product_id: str, data: Dict[str, Any]) -> None:
        """Update an existing SupplierProduct from real Basalam webhook payload."""
        from src.domains.products.models import SupplierProduct

        stmt = select(SupplierProduct).where(
            SupplierProduct.external_product_id == product_id
        )
        result = await self.db_session.execute(stmt)
        product = result.scalar_one_or_none()

        if product:
            status = self._map_status(data)
            if "title" in data:
                product.title = data["title"]
            if "description" in data:
                product.description = data["description"]
            product.status = status
            product.raw_payload = data
        else:
            logger.warning(f"Product not found for update: {product_id}")
            await self._create_product(product_id, data)

    @staticmethod
    def _map_status(data: Dict[str, Any]) -> str:
        """Map Basalam status field to internal status.

        Basalam returns status as {"value": 2976, "name": "active"} or numeric.
        2976 = active
        """
        status_field = data.get("status")
        if isinstance(status_field, dict):
            value = status_field.get("value")
            return "active" if value == 2976 else str(value)
        if isinstance(status_field, (int, float)):
            return "active" if status_field == 2976 else str(status_field)
        return str(status_field) if status_field else "active"
