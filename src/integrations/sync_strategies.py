"""
Sync Strategy Factory
=====================
Wires entity-type sync strategies for use with SyncService.

This module lives in the integration layer so the shops domain
remains free of cross-domain imports.  Callers build strategies
here and inject them into SyncService.
"""

from typing import Dict, Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.shops.models import ShopIntegration
from src.domains.shops.service.sync_service import SyncStrategy

logger = structlog.get_logger(__name__)


class ProductSyncStrategy:
    """Sync products from the supplier platform via Basalam API."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def __call__(self, integration: ShopIntegration) -> Dict[str, Any]:
        from src.integrations.basalam.client import BasalamClient
        from src.integrations.basalam.product_sync import ProductSyncService

        credentials = integration.credentials or {}
        if not credentials.get("client_id"):
            raise ValueError("Missing client_id in integration credentials")
        if not credentials.get("client_secret"):
            raise ValueError("Missing client_secret in integration credentials")

        client = BasalamClient(
            client_id=credentials["client_id"],
            client_secret=credentials["client_secret"],
            access_token=credentials.get("access_token"),
            refresh_token=credentials.get("refresh_token"),
        )
        try:
            sync_service = ProductSyncService(
                session=self.session,
                client=client,
                integration_id=integration.id,
            )
            result = await sync_service.sync_products()
            logger.info(
                "product_sync_completed",
                integration_id=str(integration.id),
                total_fetched=result.total_fetched,
                created=result.created_count,
                updated=result.updated_count,
                failed=result.failed_count,
            )
            return {
                "created_count": result.created_count,
                "updated_count": result.updated_count,
                "failed_count": result.failed_count,
            }
        finally:
            try:
                await client.close()
            except Exception:
                logger.warning("basalam_client_close_failed", exc_info=True)


class InventorySyncStrategy:
    """Sync inventory levels from the supplier platform."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def __call__(self, integration: ShopIntegration) -> Dict[str, Any]:
        from src.domains.inventory.service.sync_service import InventorySyncService

        sync_service = InventorySyncService(session=self.session)
        result = await sync_service.sync_from_supplier(integration.id)

        logger.info(
            "inventory_sync_completed",
            integration_id=str(integration.id),
            variants_updated=result.variants_updated,
            total_variants=result.total_variants,
            success=result.success,
        )
        return {
            "updated_count": result.variants_updated,
            "failed_count": (
                (result.total_variants - result.variants_updated)
                if not result.success
                else 0
            ),
            "error": "; ".join(result.errors) if result.errors else None,
        }


class OrderSyncStrategy:
    """Fetch and sync orders from the supplier platform."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def __call__(self, integration: ShopIntegration) -> Dict[str, Any]:
        from src.domains.orders.service.order_service import OrderService
        from src.integrations.shop.connectors.basalam_connector import BasalamConnector

        credentials = integration.credentials or {}
        connector = BasalamConnector(credentials=credentials)
        if integration.external_shop_id:
            connector.set_vendor_id(integration.external_shop_id)
        await connector.connect(credentials)

        try:
            external_orders = await connector.get_orders()

            order_service = OrderService(session=self.session)
            created_count = 0
            skipped_count = 0
            errors = []

            for external_order in external_orders:
                try:
                    existing = await order_service.get_order_by_external_id(
                        integration.shop_id,
                        str(external_order.order_id),
                    )

                    if existing:
                        skipped_count += 1
                    else:
                        items = [
                            {
                                "variant_id": item.variant_id,
                                "quantity": item.quantity,
                            }
                            for item in external_order.items
                            if item.variant_id
                        ]

                        if items:
                            await order_service.create_order(
                                shop_id=integration.shop_id,
                                items=items,
                                customer_data=external_order.customer,
                                external_order_id=str(external_order.order_id),
                                shipping_price=external_order.shipping_price,
                            )
                            created_count += 1
                except Exception as e:
                    errors.append(f"Order {external_order.order_id}: {str(e)}")
                    logger.warning(
                        "order_sync_item_failed",
                        order_id=external_order.order_id,
                        error=str(e),
                    )

            failed_count = len(errors)
            logger.info(
                "order_sync_completed",
                integration_id=str(integration.id),
                total_orders=len(external_orders),
                created=created_count,
                skipped=skipped_count,
                failed=failed_count,
            )
            return {
                "created_count": created_count,
                "skipped_count": skipped_count,
                "failed_count": failed_count,
                "error": "; ".join(errors) if errors else None,
            }
        finally:
            try:
                await connector.disconnect()
            except Exception:
                logger.warning("connector_disconnect_failed", exc_info=True)


def create_basalam_sync_strategies(
    session: AsyncSession,
) -> Dict[str, SyncStrategy]:
    """Build sync strategies for all Basalam entity types."""
    return {
        "product": ProductSyncStrategy(session),
        "inventory": InventorySyncStrategy(session),
        "order": OrderSyncStrategy(session),
    }
