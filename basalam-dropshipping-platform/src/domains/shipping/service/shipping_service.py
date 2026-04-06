"""
Shipping Service
================
Business logic for shipment creation, tracking, and carrier integration.

Coordinates between:
- Shipment model (orders/models.py) and its repository
- ShippingMethod model (shops/models.py) for available methods
- Shop connector (integrations/shop/) for Basalam API calls
"""
import structlog
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.orders.models import Shipment
from src.domains.orders.repository.shipment import ShipmentRepository
from src.domains.shops.models import ShippingMethod
from src.domains.shipping.repository.shipping_method_repository import ShippingMethodRepository

logger = structlog.get_logger(__name__)


class ShippingService:
    """
    Service for managing shipping operations.

    Handles:
    - Syncing shipping methods from Basalam
    - Creating shipments when payment is captured
    - Updating tracking information
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self._shipment_repo = ShipmentRepository(session)
        self._method_repo = ShippingMethodRepository(session)

    # ---------------------------------------------------------------
    # Shipping Method Sync
    # ---------------------------------------------------------------

    async def sync_shipping_methods(
        self,
        platform_id: UUID,
        connector: Any,
    ) -> Dict[str, int]:
        """
        Sync available shipping methods from a platform connector.

        Args:
            platform_id: UUID of the platform to sync methods for
            connector: ShopConnectorPort instance with fetch_shipping_methods()

        Returns:
            Dict with synced count
        """
        methods_data = await connector.fetch_shipping_methods()
        synced = 0

        for method_data in methods_data:
            await self._method_repo.upsert_from_sync(
                platform_id=platform_id,
                external_id=str(method_data.get("id", "")),
                name=method_data.get("name", "Unknown"),
                shipping_type=method_data.get("type", "standard"),
            )
            synced += 1

        logger.info(
            "shipping_methods_synced",
            platform_id=str(platform_id),
            count=synced,
        )
        return {"synced": synced}

    # ---------------------------------------------------------------
    # Shipment Creation
    # ---------------------------------------------------------------

    async def create_shipment(
        self,
        order_id: UUID,
        order_item_id: UUID,
        shipping_method_id: Optional[UUID] = None,
        connector: Optional[Any] = None,
    ) -> Shipment:
        """
        Create a shipment record after payment is captured.

        If a connector is provided, also creates the shipment on the
        supplier's platform (Basalam).

        Args:
            order_id: UUID of the order
            order_item_id: UUID of the order item
            shipping_method_id: Optional shipping method to use
            connector: Optional ShopConnectorPort for platform API calls

        Returns:
            Created Shipment record
        """
        shipment_data = {
            "id": uuid4(),
            "order_id": order_id,
            "order_item_id": order_item_id,
            "shipping_method_id": shipping_method_id,
            "status": "pending",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

        shipment = await self._shipment_repo.create(shipment_data)

        # Attempt to create shipment on supplier platform
        if connector and shipping_method_id:
            method = await self._method_repo.get_by_id(shipping_method_id)
            try:
                result = await connector.create_shipment(
                    order_id=str(order_id),
                    shipping_method=method.shipping_type if method else "standard",
                )
                if result:
                    await self._shipment_repo.update(
                        shipment.id,
                        {
                            "tracking_code": result.get("tracking_code"),
                            "carrier": result.get("carrier"),
                            "status": "label_created",
                        },
                    )
                    shipment = await self._shipment_repo.get_by_id(shipment.id)
                    logger.info(
                        "shipment_created_on_platform",
                        shipment_id=str(shipment.id),
                        tracking_code=result.get("tracking_code"),
                    )
            except NotImplementedError:
                logger.warning(
                    "connector_does_not_support_shipment_creation",
                    connector=connector.__class__.__name__,
                )
            except Exception as e:
                logger.error(
                    "failed_to_create_shipment_on_platform",
                    shipment_id=str(shipment.id),
                    error=str(e),
                )

        return shipment

    # ---------------------------------------------------------------
    # Tracking
    # ---------------------------------------------------------------

    async def update_tracking(
        self,
        shipment_id: UUID,
        tracking_code: Optional[str] = None,
        carrier: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Optional[Shipment]:
        """
        Update tracking information for a shipment.

        Args:
            shipment_id: UUID of the shipment
            tracking_code: New tracking code
            carrier: Carrier name
            status: New status

        Returns:
            Updated Shipment or None
        """
        update_data: Dict[str, Any] = {}

        if tracking_code:
            update_data["tracking_code"] = tracking_code
        if carrier:
            update_data["carrier"] = carrier
        if status:
            update_data["status"] = status

            # Set timestamps based on status
            now = datetime.now(timezone.utc)
            if status == "shipped" and "shipped_at" not in update_data:
                update_data["shipped_at"] = now
            elif status == "delivered":
                update_data["delivered_at"] = now
                update_data["actual_delivery"] = now

        if not update_data:
            return await self._shipment_repo.get_by_id(shipment_id)

        shipment = await self._shipment_repo.update(shipment_id, update_data)

        if shipment:
            logger.info(
                "shipment_tracking_updated",
                shipment_id=str(shipment_id),
                status=status,
                tracking_code=tracking_code,
            )

        return shipment

    async def get_shipments_for_order(self, order_id: UUID) -> List[Shipment]:
        """Get all shipments for an order."""
        return await self._shipment_repo.get_by_order(order_id)

    async def get_pending_deliveries(self) -> List[Shipment]:
        """Get all shipments awaiting delivery (for auto-confirmation job)."""
        return await self._shipment_repo.get_pending_delivery()

    async def confirm_delivery(
        self,
        shipment_id: UUID,
        confirmed_by: str = "customer",
    ) -> Optional[Shipment]:
        """
        Confirm delivery of a shipment.

        Args:
            shipment_id: UUID of the shipment
            confirmed_by: Who confirmed (customer, carrier, auto)
        """
        now = datetime.now(timezone.utc)
        return await self._shipment_repo.update(shipment_id, {
            "status": "delivered",
            "delivered_at": now,
            "delivery_confirmed_at": now,
            "delivery_confirmed_by": confirmed_by,
            "actual_delivery": now,
        })
