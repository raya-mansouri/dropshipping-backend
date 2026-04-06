"""
Inventory Sync Service
======================
Business logic for syncing inventory with supplier platforms
"""

import structlog
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models import InventoryLog, InventoryReconciliation, InventorySource
from ..repository import (
    InventoryRepository,
    InventoryLogRepository,
)
from src.domains.shops.repository import ShopIntegrationRepository
from src.domains.shops.models import ShopIntegration
from src.core.events.publisher import EventPublisher
from src.core.events.base import DomainEvent
from src.core.events.inventory import (
    InventoryUpdated,
    InventorySyncCompleted,
)

logger = structlog.get_logger(__name__)


@dataclass
class SyncResult:
    """Result of inventory sync operation"""

    success: bool
    integration_id: uuid.UUID
    variants_updated: int
    total_variants: int
    errors: List[str] = field(default_factory=list)
    details: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ReconciliationResult:
    """Result of inventory reconciliation"""

    success: bool
    integration_id: uuid.UUID
    total_variants: int
    matched_count: int
    mismatch_count: int
    fixed_count: int
    errors: List[str] = field(default_factory=list)
    details: List[Dict[str, Any]] = field(default_factory=list)


class InventorySyncService:
    """
    Service for syncing inventory with supplier platforms.

    Handles fetching inventory from Basalam, updating local records,
    and performing reconciliation to fix mismatches.
    """

    def __init__(
        self,
        session: AsyncSession,
        basalam_client: Any = None,
        event_publisher: Optional[EventPublisher] = None,
    ):
        """
        Initialize service with database session.

        Args:
            session: Async SQLAlchemy session for database operations
            basalam_client: Optional Basalam client for API calls
            event_publisher: Optional EventPublisher for domain events
        """
        self.session = session
        self.basalam_client = basalam_client
        self._event_publisher = event_publisher
        self._inventory_repo = InventoryRepository(session)
        self._log_repo = InventoryLogRepository(session)
        self._integration_repo = ShopIntegrationRepository(session)

    async def _publish_event(self, event: DomainEvent) -> None:
        """Safely publish domain event. Non-blocking - failures are logged but don't raise."""
        if self._event_publisher is None:
            return
        try:
            await self._event_publisher.publish(topic="events", event=event)
        except Exception as e:
            logger.warning("failed_to_publish_event", event_type=event.event_type, error=str(e))

    async def _get_basalam_client(self, integration_id: uuid.UUID) -> Any:
        """Get or create Basalam client for integration."""
        if self.basalam_client:
            return self.basalam_client

        from src.integrations.basalam.client import BasalamClient

        integration = await self._integration_repo.get_by_id(integration_id)
        if not integration:
            raise ValueError(f"Integration {integration_id} not found")

        credentials = integration.credentials_encrypted or {}
        client = BasalamClient(
            client_id=credentials.get("client_id", ""),
            client_secret=credentials.get("client_secret", ""),
            access_token=credentials.get("access_token"),
            refresh_token=credentials.get("refresh_token"),
        )
        return client

    async def sync_from_supplier(self, integration_id: uuid.UUID) -> SyncResult:
        """
        Sync inventory from supplier (Basalam) to local database.

        Fetches current inventory from Basalam API and updates
        SupplierVariant records. Creates audit log entries for
        all changes.

        Args:
            integration_id: UUID of the shop integration

        Returns:
            SyncResult with operation details
        """
        from src.domains.products.models import SupplierProduct, SupplierVariant

        errors: List[str] = []
        details: List[Dict[str, Any]] = []
        variants_updated = 0
        total_variants = 0

        try:
            integration = await self._integration_repo.get_by_id(integration_id)
            if not integration:
                return SyncResult(
                    success=False,
                    integration_id=integration_id,
                    variants_updated=0,
                    total_variants=0,
                    errors=[f"Integration {integration_id} not found"],
                )

            result = await self.session.execute(
                select(SupplierVariant)
                .join(SupplierProduct)
                .where(
                    SupplierProduct.shop_id == integration.shop_id,
                    SupplierVariant.status == "active",
                )
            )
            variants = list(result.scalars().all())
            total_variants = len(variants)

            client = await self._get_basalam_client(integration_id)

            for variant in variants:
                try:
                    product_id = (
                        variant.raw_payload.get("product_id")
                        if variant.raw_payload
                        else None
                    )
                    if not product_id:
                        continue

                    inventory_data = await client.get_inventory(product_id)
                    supplier_variants = inventory_data.get("variants", [])

                    supplier_variant = next(
                        (
                            v
                            for v in supplier_variants
                            if v.get("variant_id") == str(variant.id)
                        ),
                        None,
                    )

                    if supplier_variant:
                        old_inventory = variant.inventory
                        new_inventory = supplier_variant.get("stock", 0)

                        if old_inventory != new_inventory:
                            await self._inventory_repo.update(
                                variant.id,
                                {
                                    "inventory": new_inventory,
                                },
                            )

                            await self._log_repo.create(
                                {
                                    "variant_id": variant.id,
                                    "old_inventory": old_inventory,
                                    "new_inventory": new_inventory,
                                    "change": new_inventory - old_inventory,
                                    "source": InventorySource.WEBHOOK.value,
                                    "reference_id": integration_id,
                                    "reference_type": "sync_job",
                                    "reason": "Synced from supplier",
                                    "metadata": {"integration_id": str(integration_id)},
                                }
                            )

                            details.append(
                                {
                                    "variant_id": str(variant.id),
                                    "old_inventory": old_inventory,
                                    "new_inventory": new_inventory,
                                }
                            )
                            variants_updated += 1

                except Exception as e:
                    errors.append(f"Error syncing variant {variant.id}: {str(e)}")

        except Exception as e:
            errors.append(f"Sync failed: {str(e)}")

        return SyncResult(
            success=len(errors) == 0,
            integration_id=integration_id,
            variants_updated=variants_updated,
            total_variants=total_variants,
            errors=errors,
            details=details,
        )

    async def reconcile(self, integration_id: uuid.UUID) -> ReconciliationResult:
        """
        Reconcile local inventory with supplier records.

        Compares local database inventory against supplier API,
        identifies mismatches, and fixes them. Logs all corrections.

        Args:
            integration_id: UUID of the shop integration

        Returns:
            ReconciliationResult with operation details
        """
        from src.domains.products.models import SupplierProduct, SupplierVariant

        errors: List[str] = []
        details: List[Dict[str, Any]] = []
        matched_count = 0
        mismatch_count = 0
        fixed_count = 0
        total_variants = 0

        try:
            integration = await self._integration_repo.get_by_id(integration_id)
            if not integration:
                return ReconciliationResult(
                    success=False,
                    integration_id=integration_id,
                    total_variants=0,
                    matched_count=0,
                    mismatch_count=0,
                    fixed_count=0,
                    errors=[f"Integration {integration_id} not found"],
                )

            result = await self.session.execute(
                select(SupplierVariant)
                .join(SupplierProduct)
                .where(
                    SupplierProduct.shop_id == integration.shop_id,
                    SupplierVariant.status == "active",
                )
            )
            variants = list(result.scalars().all())
            total_variants = len(variants)

            client = await self._get_basalam_client(integration_id)

            for variant in variants:
                try:
                    product_id = (
                        variant.raw_payload.get("product_id")
                        if variant.raw_payload
                        else None
                    )
                    if not product_id:
                        continue

                    inventory_data = await client.get_inventory(product_id)
                    supplier_variants = inventory_data.get("variants", [])

                    supplier_variant = next(
                        (
                            v
                            for v in supplier_variants
                            if v.get("variant_id") == str(variant.id)
                        ),
                        None,
                    )

                    if not supplier_variant:
                        continue

                    db_inventory = variant.inventory
                    supplier_inventory = supplier_variant.get("stock", 0)

                    if db_inventory == supplier_inventory:
                        matched_count += 1
                    else:
                        mismatch_count += 1
                        details.append(
                            {
                                "variant_id": str(variant.id),
                                "db_inventory": db_inventory,
                                "supplier_inventory": supplier_inventory,
                                "action": "fixing",
                            }
                        )

                        old_inventory = db_inventory
                        await self._inventory_repo.update(
                            variant.id,
                            {
                                "inventory": supplier_inventory,
                            },
                        )

                        await self._log_repo.create(
                            {
                                "variant_id": variant.id,
                                "old_inventory": old_inventory,
                                "new_inventory": supplier_inventory,
                                "change": supplier_inventory - old_inventory,
                                "source": InventorySource.RECONCILIATION.value,
                                "reference_id": integration_id,
                                "reference_type": "reconciliation",
                                "reason": f"Reconciliation: DB {old_inventory} vs Supplier {supplier_inventory}",
                                "metadata": {"integration_id": str(integration_id)},
                            }
                        )
                        fixed_count += 1

                except Exception as e:
                    errors.append(f"Error reconciling variant {variant.id}: {str(e)}")

        except Exception as e:
            errors.append(f"Reconciliation failed: {str(e)}")

        return ReconciliationResult(
            success=len(errors) == 0,
            integration_id=integration_id,
            total_variants=total_variants,
            matched_count=matched_count,
            mismatch_count=mismatch_count,
            fixed_count=fixed_count,
            errors=errors,
            details=details,
        )
