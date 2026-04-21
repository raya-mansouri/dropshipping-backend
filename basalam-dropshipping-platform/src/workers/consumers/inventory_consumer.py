"""
Inventory Kafka Consumer
========================
Consumes inventory events and triggers business operations:
- Low inventory threshold checks and alerts
- Reservation audit logging
- Sync completion tracking
"""

import structlog
from datetime import datetime, timezone
from typing import Dict, Any
from uuid import uuid4

from src.workers.consumers.base import DLQAwareConsumer
from src.core.database import async_session_maker

logger = structlog.get_logger("workers.inventory_consumer")

LOW_INVENTORY_THRESHOLD = 5


class InventoryConsumer(DLQAwareConsumer):
    topic = "inventory.updated"
    group_id = "inventory-consumer-group"

    async def process_message(self, message) -> None:
        event = message.value
        event_type = event.get("event_type")
        await self._handle_event(event_type, event)

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
            logger.warning("Unknown inventory event type", event_type=event_type)

    async def _handle_inventory_updated(self, event: Dict[str, Any]):
        metadata = event.get("metadata", {})
        variant_id = metadata.get("variant_id")
        old_quantity = metadata.get("old_quantity")
        new_quantity = metadata.get("new_quantity")
        source = metadata.get("source")

        if not variant_id:
            logger.warning("InventoryUpdated event missing variant_id")
            return

        logger.info(
            "Processing InventoryUpdated",
            variant_id=str(variant_id),
            old_quantity=old_quantity,
            new_quantity=new_quantity,
            source=source,
        )

        async with async_session_maker() as session:
            # Check low inventory threshold
            if new_quantity is not None and new_quantity <= LOW_INVENTORY_THRESHOLD:
                try:
                    await self._check_and_notify_low_inventory(
                        session, variant_id, new_quantity
                    )
                except Exception as e:
                    logger.error(
                        "low_inventory_notification_failed",
                        variant_id=str(variant_id),
                        error=str(e),
                    )

            await session.commit()

    async def _check_and_notify_low_inventory(
        self, session, variant_id, current_quantity
    ):
        """Send low-inventory notification if quantity is at or below threshold."""
        from src.integrations.notification.manager import create_notification_manager
        from src.integrations.notification.ports import (
            NotificationChannel,
            NotificationRecipient,
            NotificationContent,
        )
        from src.domains.products.models import SupplierVariant, SupplierProduct
        from src.domains.shops.models import Shop
        from sqlalchemy import select

        notification_mgr = create_notification_manager({})

        result = await session.execute(
            select(SupplierVariant)
            .join(
                SupplierProduct,
                SupplierProduct.id == SupplierVariant.supplier_product_id,
            )
            .where(SupplierVariant.id == variant_id)
        )
        variant = result.scalar_one_or_none()

        if not variant:
            return

        product = variant.product
        if not product:
            return

        shop_result = await session.execute(
            select(Shop).where(Shop.id == product.shop_id)
        )
        shop = shop_result.scalar_one_or_none()
        if not shop:
            return

        recipient = NotificationRecipient(user_id=shop.account_id)
        content = NotificationContent(
            title="Low Inventory Alert",
            body=(
                f"Product '{product.title}' variant inventory is low: "
                f"{current_quantity} remaining."
            ),
            template_id="inventory_low",
            variables={
                "product_id": str(product.id),
                "product_name": product.title,
                "variant_id": str(variant_id),
                "quantity": current_quantity,
            },
            action_url=f"/products/{product.id}",
        )
        await notification_mgr.send(
            channel=NotificationChannel.IN_APP,
            recipient=recipient,
            content=content,
        )

        logger.info(
            "Sent low inventory notification",
            variant_id=str(variant_id),
            product_id=str(product.id),
            quantity=current_quantity,
        )

    async def _handle_inventory_reserved(self, event: Dict[str, Any]):
        metadata = event.get("metadata", {})
        variant_id = metadata.get("variant_id")
        order_item_id = metadata.get("order_item_id")
        quantity = metadata.get("quantity")
        expires_at = metadata.get("expires_at")

        if not variant_id:
            logger.warning("InventoryReserved event missing variant_id")
            return

        logger.info(
            "Processing InventoryReserved",
            variant_id=str(variant_id),
            order_item_id=str(order_item_id),
            quantity=quantity,
            expires_at=expires_at,
        )

        async with async_session_maker() as session:
            from src.domains.inventory.repository import InventoryLogRepository

            log_repo = InventoryLogRepository(session)
            await log_repo.create(
                {
                    "variant_id": variant_id,
                    "old_inventory": metadata.get("old_available", 0),
                    "new_inventory": metadata.get("new_available", 0),
                    "change": -(quantity or 0),
                    "source": "order",
                    "reference_id": order_item_id,
                    "reference_type": "order_item",
                    "reason": f"Reserved {quantity} units for order item",
                    "extra_data": {
                        "event": "InventoryReserved",
                        "expires_at": expires_at,
                    },
                }
            )
            await session.commit()

            logger.info(
                "Recorded inventory reservation in audit log",
                variant_id=str(variant_id),
                order_item_id=str(order_item_id),
            )

    async def _handle_inventory_released(self, event: Dict[str, Any]):
        metadata = event.get("metadata", {})
        variant_id = metadata.get("variant_id")
        order_item_id = metadata.get("order_item_id")
        quantity = metadata.get("quantity")
        reason = metadata.get("reason")

        if not variant_id:
            logger.warning("InventoryReleased event missing variant_id")
            return

        logger.info(
            "Processing InventoryReleased",
            variant_id=str(variant_id),
            order_item_id=str(order_item_id),
            quantity=quantity,
            reason=reason,
        )

        async with async_session_maker() as session:
            from src.domains.inventory.repository import InventoryLogRepository

            log_repo = InventoryLogRepository(session)
            await log_repo.create(
                {
                    "variant_id": variant_id,
                    "old_inventory": metadata.get("old_available", 0),
                    "new_inventory": metadata.get("new_available", 0),
                    "change": quantity or 0,
                    "source": "correction",
                    "reference_id": order_item_id,
                    "reference_type": "order_item",
                    "reason": f"Released reservation: {reason or 'unknown'}",
                    "extra_data": {"event": "InventoryReleased", "reason": reason},
                }
            )
            await session.commit()

            logger.info(
                "Recorded inventory release in audit log",
                variant_id=str(variant_id),
                order_item_id=str(order_item_id),
                reason=reason,
            )

    async def _handle_inventory_sync_completed(self, event: Dict[str, Any]):
        metadata = event.get("metadata", {})
        integration_id = metadata.get("integration_id")
        variants_synced = metadata.get("variants_synced")
        errors = metadata.get("errors", [])

        if not integration_id:
            logger.warning("InventorySyncCompleted event missing integration_id")
            return

        logger.info(
            "Processing InventorySyncCompleted",
            integration_id=str(integration_id),
            variants_synced=variants_synced,
            errors_count=len(errors) if errors else 0,
        )

        async with async_session_maker() as session:
            from src.domains.inventory.models import InventoryReconciliation

            reconciliation = InventoryReconciliation(
                id=uuid4(),
                integration_id=integration_id,
                status="completed",
                total_variants=variants_synced or 0,
                matched_count=(variants_synced or 0) - len(errors or []),
                mismatch_count=len(errors or []),
                errors=errors or [],
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
            )
            session.add(reconciliation)
            await session.commit()

            logger.info(
                "Recorded inventory sync completion",
                integration_id=str(integration_id),
                variants_synced=variants_synced,
                error_count=len(errors) if errors else 0,
            )
