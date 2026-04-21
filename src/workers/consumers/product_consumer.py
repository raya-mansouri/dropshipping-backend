"""
Product Kafka Consumer
======================
Consumes product events and triggers business operations:
- Product creation logging via audit trail
- Forbidden product notifications to shop owners
- Sync result tracking with timestamp updates
"""

import structlog
from datetime import datetime, timezone
from typing import Dict, Any
from uuid import uuid4

from src.workers.consumers.base import DLQAwareConsumer
from src.core.database import async_session_maker
from src.domains.audit_logs.models import AuditLog
from src.integrations.notification.manager import create_notification_manager
from src.integrations.notification.ports import (
    NotificationChannel,
    NotificationRecipient,
    NotificationContent,
)
from src.domains.products.models import SupplierProduct
from src.domains.shops.models import Shop
from sqlalchemy import select, update

logger = structlog.get_logger("workers.product_consumer")


class ProductConsumer(DLQAwareConsumer):
    topic = "product.updated"
    group_id = "product-consumer-group"

    async def process_message(self, message) -> None:
        event = message.value
        event_type = event.get("event_type")
        await self._handle_event(event_type, event)

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
            logger.warning("Unknown product event type", event_type=event_type)

    async def _handle_product_created(self, event: Dict[str, Any]):
        product_id = event.get("metadata", {}).get("product_id")
        shop_id = event.get("metadata", {}).get("shop_id")
        title = event.get("metadata", {}).get("title")

        if not product_id:
            logger.warning("ProductCreated event missing product_id")
            return

        logger.info(
            "Product created",
            product_id=str(product_id),
            shop_id=str(shop_id),
            title=title,
        )

        async with async_session_maker() as session:
            audit = AuditLog(
                id=uuid4(),
                entity_type="product",
                entity_id=product_id,
                action="created",
                actor_type="system",
                actor_id=shop_id,
                new_value={
                    "title": title,
                    "shop_id": str(shop_id) if shop_id else None,
                },
                created_at=datetime.now(timezone.utc),
            )
            session.add(audit)
            await session.commit()

            logger.info(
                "Recorded product creation in audit log",
                product_id=str(product_id),
            )

    async def _handle_product_updated(self, event: Dict[str, Any]):
        product_id = event.get("metadata", {}).get("product_id")
        changes = event.get("metadata", {}).get("changes", {})

        if not product_id:
            logger.warning("ProductUpdated event missing product_id")
            return

        logger.info(
            "Product updated",
            product_id=str(product_id),
            changes=changes,
        )

        new_status = changes.get("status") if isinstance(changes, dict) else None
        if new_status == "forbidden":
            try:
                await self._notify_product_forbidden(product_id, event)
            except Exception as e:
                logger.error(
                    "product_forbidden_notification_failed",
                    product_id=str(product_id),
                    error=str(e),
                )

    async def _handle_product_status_changed(self, event: Dict[str, Any]):
        product_id = event.get("metadata", {}).get("product_id")
        old_status = event.get("metadata", {}).get("old_status")
        new_status = event.get("metadata", {}).get("new_status")

        if not product_id:
            logger.warning("ProductStatusChanged event missing product_id")
            return

        logger.info(
            "Product status changed",
            product_id=str(product_id),
            old_status=old_status,
            new_status=new_status,
        )

        if new_status == "forbidden":
            try:
                await self._notify_product_forbidden(product_id, event)
            except Exception as e:
                logger.error(
                    "product_forbidden_notification_failed",
                    product_id=str(product_id),
                    error=str(e),
                )

    async def _notify_product_forbidden(self, product_id, event: Dict[str, Any]):
        """Send notification when a product becomes forbidden."""
        async with async_session_maker() as session:
            notification_mgr = create_notification_manager({})

            product_result = await session.execute(
                select(SupplierProduct).where(SupplierProduct.id == product_id)
            )
            product = product_result.scalar_one_or_none()

            if product:
                shop_result = await session.execute(
                    select(Shop).where(Shop.id == product.shop_id)
                )
                shop = shop_result.scalar_one_or_none()

                if shop:
                    reason = (
                        product.basalam_validation_error
                        and product.basalam_validation_error.get("message")
                    ) or event.get("metadata", {}).get(
                        "reason", "Product flagged as forbidden"
                    )

                    recipient = NotificationRecipient(user_id=shop.account_id)
                    content = NotificationContent(
                        title=f"Product Forbidden: {product.title}",
                        body=(
                            f"Product '{product.title}' has been flagged as forbidden. "
                            f"Reason: {reason}"
                        ),
                        template_id="product_forbidden",
                        variables={
                            "product_id": str(product_id),
                            "product_name": product.title,
                            "reason": str(reason),
                        },
                        action_url=f"/products/{product_id}",
                    )
                    await notification_mgr.send(
                        channel=NotificationChannel.IN_APP,
                        recipient=recipient,
                        content=content,
                    )

            await session.commit()

    async def _handle_product_deleted(self, event: Dict[str, Any]):
        product_id = event.get("metadata", {}).get("product_id")

        if not product_id:
            logger.warning("ProductDeleted event missing product_id")
            return

        logger.info("Product deleted", product_id=str(product_id))

        async with async_session_maker() as session:
            audit = AuditLog(
                id=uuid4(),
                entity_type="product",
                entity_id=product_id,
                action="deleted",
                actor_type="system",
                new_value={"event": "ProductDeleted"},
                created_at=datetime.now(timezone.utc),
            )
            session.add(audit)
            await session.commit()

    async def _handle_product_synced(self, event: Dict[str, Any]):
        product_id = event.get("metadata", {}).get("product_id")
        basalam_product_id = event.get("metadata", {}).get("basalam_product_id")
        sync_errors = event.get("metadata", {}).get("errors", [])

        if not product_id:
            logger.warning("ProductSynced event missing product_id")
            return

        logger.info(
            "Product synced",
            product_id=str(product_id),
            basalam_product_id=str(basalam_product_id),
            errors_count=len(sync_errors) if sync_errors else 0,
        )

        async with async_session_maker() as session:
            await session.execute(
                update(SupplierProduct)
                .where(SupplierProduct.id == product_id)
                .values(last_synced_at=datetime.now(timezone.utc))
            )
            await session.commit()

            logger.info(
                "Updated product sync timestamp",
                product_id=str(product_id),
            )
