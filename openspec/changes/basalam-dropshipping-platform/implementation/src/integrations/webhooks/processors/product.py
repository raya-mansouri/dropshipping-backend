"""
Product Webhook Processor
=========================
Handles product.created and product.updated events from supplier platforms.
"""

from typing import Dict, Any
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base import WebhookProcessor


logger = logging.getLogger(__name__)


class ProductWebhookProcessor(WebhookProcessor):
    """
    Processes product-related webhook events.

    Handles:
    - product.created: Create new SupplierProduct
    - product.updated: Update existing SupplierProduct
    """

    def __init__(self, secret: str, db_session: AsyncSession):
        super().__init__(secret)
        self.db_session = db_session

    async def process(self, payload: Dict[str, Any], headers: Dict[str, str]) -> bool:
        """
        Process product webhook event.

        Expected payload structure:
        {
            "event_type": "product.created" | "product.updated",
            "data": {
                "product_id": "supplier-product-123",
                "title": "Product Name",
                "description": "Product description",
                "price": 29.99,
                "images": ["https://..."],
                "variants": [...],
                "status": "active"
            }
        }
        """
        event_type = self.get_event_type(payload, headers)

        if event_type not in ("product.created", "product.updated"):
            logger.warning(f"Unexpected event type: {event_type}")
            return False

        event_data = self.extract_event_data(payload)

        product_id = event_data.get("product_id")
        if not product_id:
            logger.error("Missing required field: product_id")
            return False

        try:
            if event_type == "product.created":
                await self._create_product(product_id, event_data)
                logger.info(f"Created product: {product_id}")
            else:
                await self._update_product(product_id, event_data)
                logger.info(f"Updated product: {product_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to process product: {e}")
            return False

    async def _create_product(self, product_id: str, data: Dict[str, Any]) -> None:
        """Create a new SupplierProduct"""
        from src.domains.suppliers.models import SupplierProduct

        product = SupplierProduct(
            external_product_id=product_id,
            title=data.get("title", ""),
            description=data.get("description", ""),
            price=data.get("price", 0.0),
            images=data.get("images", []),
            status=data.get("status", "active"),
        )
        self.db_session.add(product)
        await self.db_session.commit()

    async def _update_product(self, product_id: str, data: Dict[str, Any]) -> None:
        """Update an existing SupplierProduct"""
        from src.domains.suppliers.models import SupplierProduct

        stmt = select(SupplierProduct).where(
            SupplierProduct.external_product_id == product_id
        )
        result = await self.db_session.execute(stmt)
        product = result.scalar_one_or_none()

        if product:
            if "title" in data:
                product.title = data["title"]
            if "description" in data:
                product.description = data["description"]
            if "price" in data:
                product.price = data["price"]
            if "images" in data:
                product.images = data["images"]
            if "status" in data:
                product.status = data["status"]
            await self.db_session.commit()
        else:
            logger.warning(f"Product not found for update: {product_id}")
            await self._create_product(product_id, data)
