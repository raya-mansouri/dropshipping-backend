"""
Product Sync Service for Basalam Integration
============================================
Handles page-based pagination, delta sync, and bulk upserts.
"""

import asyncio
import structlog
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from uuid import UUID

from sqlalchemy import select, and_, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.products.models import SupplierProduct, ProductVariant, SupplierVariant
from src.domains.shops.models import ShopIntegration, SyncState
from src.domains.shops.repository.sync_state import SyncStateRepository
from src.integrations.basalam.client import BasalamClient
from src.integrations.basalam.exceptions import BasalamAPIError, ForbiddenProductError

logger = structlog.get_logger(__name__)


class ProductSyncResult:
    """Result of a product sync operation."""

    def __init__(
        self,
        total_fetched: int = 0,
        created_count: int = 0,
        updated_count: int = 0,
        failed_count: int = 0,
        batches_processed: int = 0,
        errors: Optional[List[str]] = None,
    ):
        self.total_fetched = total_fetched
        self.created_count = created_count
        self.updated_count = updated_count
        self.failed_count = failed_count
        self.batches_processed = batches_processed
        self.errors = errors or []

    def __repr__(self) -> str:
        return (
            f"ProductSyncResult(fetched={self.total_fetched}, "
            f"created={self.created_count}, updated={self.updated_count}, "
            f"failed={self.failed_count}, batches={self.batches_processed})"
        )


class ProductSyncService:
    """
    Service for syncing products from Basalam.

    Features:
    - Page-based pagination for API requests
    - Delta sync using updated_at_min timestamps
    - Full sync mode when needed
    - Bulk upserts with ON CONFLICT DO UPDATE
    - Batch processing with configurable batch size
    - Concurrent batch processing with asyncio.gather
    """

    BATCH_SIZE = 100
    MAX_CONCURRENT_BATCHES = 5
    DEFAULT_PER_PAGE = 50
    MAX_PER_PAGE = 100

    def __init__(
        self,
        session: AsyncSession,
        client: BasalamClient,
        integration_id: UUID,
    ):
        self.session = session
        self.client = client
        self.integration_id = integration_id
        self._sync_state_repo = SyncStateRepository(session)
        self._sync_state: Optional[SyncState] = None
        self._shop_id: Optional[UUID] = None
        self._integration: Optional[ShopIntegration] = None

    async def _ensure_integration_loaded(self) -> ShopIntegration:
        """Ensure integration and shop_id are loaded from database."""
        if self._integration is None:
            result = await self.session.execute(
                select(ShopIntegration).where(ShopIntegration.id == self.integration_id)
            )
            self._integration = result.scalar_one_or_none()
            if self._integration:
                self._shop_id = self._integration.shop_id
        return self._integration

    async def _get_or_create_sync_state(
        self, entity_type: str = "product"
    ) -> SyncState:
        """Get or create sync state for this integration using SyncStateRepository."""
        sync_state = await self._sync_state_repo.get_or_create(
            self.integration_id, entity_type
        )
        return sync_state

    async def _update_sync_state(
        self,
        sync_state: SyncState,
        cursor_token: Optional[str] = None,
        last_sync_timestamp: Optional[datetime] = None,
        created: int = 0,
        updated: int = 0,
        failed: int = 0,
        status: str = "syncing",
        error: Optional[str] = None,
    ) -> None:
        """Update sync state after a sync operation."""
        if cursor_token is not None:
            sync_state.cursor_token = cursor_token
        if last_sync_timestamp is not None:
            sync_state.last_sync_timestamp = last_sync_timestamp
        if created > 0 or updated > 0 or failed > 0:
            sync_state.created_count += created
            sync_state.updated_count += updated
            sync_state.failed_count += failed
            sync_state.total_synced += created + updated + failed
        if status:
            sync_state.status = status
        if error is not None:
            sync_state.last_error = error

        await self.session.flush()

    async def sync_products(
        self,
        full_sync: bool = False,
        batch_size: int = BATCH_SIZE,
        per_page: int = DEFAULT_PER_PAGE,
    ) -> ProductSyncResult:
        """
        Sync products from Basalam using cursor-based pagination.

        Args:
            full_sync: If True, ignore last sync timestamp and fetch all products
            batch_size: Number of records per database batch
            per_page: Number of products per API request

        Returns:
            ProductSyncResult with sync statistics
        """
        logger.info(
            "starting_product_sync",
            integration_id=str(self.integration_id),
            full_sync=full_sync,
        )

        sync_state = await self._get_or_create_sync_state("product")

        if full_sync:
            sync_state.sync_mode = "full"
            await self._update_sync_state(
                sync_state, status="syncing", cursor_token=None
            )
        else:
            sync_state.sync_mode = "delta"
            await self._update_sync_state(sync_state, status="syncing")

        try:
            result = await self._fetch_and_process_products(
                sync_state=sync_state,
                full_sync=full_sync,
                batch_size=batch_size,
                per_page=per_page,
            )

            await self._update_sync_state(
                sync_state,
                last_sync_timestamp=datetime.utcnow(),
                cursor_token=None,
                created=result.created_count,
                updated=result.updated_count,
                failed=result.failed_count,
                status="idle",
            )

            logger.info("product_sync_completed", result=str(result))

            return result

        except Exception as e:
            error_msg = f"Product sync failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            await self._update_sync_state(
                sync_state,
                status="error",
                error=error_msg,
            )
            raise

    async def _fetch_and_process_products(
        self,
        sync_state: SyncState,
        full_sync: bool,
        batch_size: int,
        per_page: int,
    ) -> ProductSyncResult:
        """Fetch products from API and process them in batches using page-based pagination."""

        last_modified = None if full_sync else sync_state.last_sync_timestamp

        result = ProductSyncResult()

        # Fetch first page to determine total pages
        response = None
        try:
            response = await self._fetch_products_page(
                page=1,
                per_page=per_page,
                last_modified=last_modified,
            )
        except ForbiddenProductError as e:
            logger.warning("forbidden_product_detected", error=str(e))
            await self._handle_forbidden_product(e)
            # Don't fail the whole sync for one forbidden product
        except BasalamAPIError as e:
            logger.error("failed_to_fetch_products_page", error=str(e))
            result.errors.append(f"API Error: {str(e)}")
            return result

        if response is None:
            # ForbiddenProductError was caught and handled; no page data available
            return result

        pagination = response.get("pagination", {})
        total_pages = pagination.get("total_page", 1)
        products = response.get("products", [])

        # Process first page
        if products:
            result.total_fetched += len(products)
            batches = self._create_batches(products, batch_size)
            result.batches_processed += len(batches)
            batch_results = await self._process_batches_concurrent(batches)
            for batch_created, batch_updated, batch_failed in batch_results:
                result.created_count += batch_created
                result.updated_count += batch_updated
                result.failed_count += batch_failed

        # Process remaining pages (2..total_pages)
        for page in range(2, total_pages + 1):
            try:
                response = await self._fetch_products_page(
                    page=page,
                    per_page=per_page,
                    last_modified=last_modified,
                )
            except BasalamAPIError as e:
                logger.error("failed_to_fetch_products_page", page=page, error=str(e))
                result.errors.append(f"API Error on page {page}: {str(e)}")
                break

            products = response.get("products", [])
            if not products:
                continue

            result.total_fetched += len(products)

            batches = self._create_batches(products, batch_size)
            result.batches_processed += len(batches)

            batch_results = await self._process_batches_concurrent(batches)

            for batch_created, batch_updated, batch_failed in batch_results:
                result.created_count += batch_created
                result.updated_count += batch_updated
                result.failed_count += batch_failed

        return result

    async def _fetch_products_page(
        self,
        page: int = 1,
        per_page: int = DEFAULT_PER_PAGE,
        last_modified: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Fetch a single page of products from Basalam API.

        Calls GET /vendors/{vendor_id}/products with page-based pagination.
        The response contains {data, total_page, page, per_page, total_count}.

        Args:
            page: Page number (1-based)
            per_page: Number of products per page
            last_modified: Filter products modified since this timestamp (delta sync)

        Returns:
            Dict with products (mapped) and pagination info (total_page, etc.)
        """
        integration = await self._ensure_integration_loaded()
        if not integration or not integration.external_shop_id:
            raise ValueError(
                f"Integration {self.integration_id} has no external_shop_id (vendor_id)"
            )

        vendor_id = integration.external_shop_id
        params: Dict[str, Any] = {
            "page": page,
            "per_page": min(per_page, self.MAX_PER_PAGE),
        }

        if last_modified:
            params["updated_at_min"] = last_modified.isoformat()

        response = await self.client._request(
            "GET",
            f"/vendors/{vendor_id}/products",
            rate_limit_endpoint="products",
            params=params,
        )

        return {
            "products": [
                self._map_basalam_product(p) for p in response.get("data", [])
            ],
            "pagination": {
                "total_page": response.get("total_page", 1),
                "page": response.get("page", page),
                "per_page": response.get("per_page", per_page),
                "total_count": response.get("total_count", 0),
            },
        }

    def _map_basalam_product(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Map real Basalam product to internal format.

        Real Basalam product shape:
        - id (not product_id)
        - photo{original, id} (not images[])
        - status{value} (numeric, 2976=active)
        - inventory (top-level)
        - is_wholesale
        """
        # Handle status: Basalam returns {value: 2976, name: "active"}
        status_field = payload.get("status", {})
        if isinstance(status_field, dict):
            status_value = status_field.get("value")
            # Map known numeric status codes
            status = "active" if status_value == 2976 else str(status_value)
        else:
            status = str(status_field) if status_field else "active"

        # Handle photo: Basalam returns {original: url, id: int}
        photo = payload.get("photo", {})
        media = []
        if photo:
            media.append({
                "url": photo.get("original", ""),
                "external_id": str(photo.get("id", "")),
                "type": "image",
                "order": 0,
            })

        return {
            "external_product_id": str(payload.get("id")),
            "title": payload.get("title"),
            "description": payload.get("description"),
            "status": status,
            "category_id": payload.get("category_id"),
            "has_variants": bool(payload.get("variants")),
            "raw_payload": payload,
            "moderation_status": payload.get("moderation_status"),
            "media": media,
            "is_wholesale": payload.get("is_wholesale", False),
            "inventory": payload.get("inventory", 0),
            "price": payload.get("price"),
            "updated_at": payload.get("updated_at"),
            "created_at": payload.get("created_at"),
            "variants": [
                self._map_basalam_variant(v, str(payload.get("id")))
                for v in payload.get("variants", [])
            ],
        }

    def _map_basalam_variant(
        self, variant: Dict[str, Any], product_id: str
    ) -> Dict[str, Any]:
        """Map real Basalam variant to internal format.

        Real Basalam variant has: id, price, inventory, attributes.
        """
        return {
            "external_variant_id": str(variant.get("id")),
            "external_product_id": product_id,
            "sku": variant.get("sku"),
            "attributes": variant.get("attributes", {}),
            "cost_price": variant.get("price", 0),
            "inventory": variant.get("inventory", variant.get("stock", 0)),
            "status": "active" if variant.get("is_active", True) else "inactive",
            "raw_payload": variant,
            "updated_at": variant.get("updated_at"),
            "created_at": variant.get("created_at"),
        }

    def _create_batches(
        self, items: List[Dict[str, Any]], batch_size: int
    ) -> List[List[Dict[str, Any]]]:
        """Split items into batches."""
        return [items[i : i + batch_size] for i in range(0, len(items), batch_size)]

    async def _process_batches_concurrent(
        self, batches: List[List[Dict[str, Any]]]
    ) -> List[Tuple[int, int, int]]:
        """
        Process batches concurrently using asyncio.gather.

        Returns:
            List of (created_count, updated_count, failed_count) tuples
        """
        semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_BATCHES)

        async def process_with_semaphore(
            batch: List[Dict[str, Any]],
        ) -> Tuple[int, int, int]:
            async with semaphore:
                return await self._process_single_batch(batch)

        tasks = [process_with_semaphore(batch) for batch in batches]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed_results = []
        for result in results:
            if isinstance(result, Exception):
                logger.error("batch_processing_failed", error=str(result))
                processed_results.append((0, 0, len(batches[0])))
            else:
                processed_results.append(result)

        return processed_results

    async def _process_single_batch(
        self, products: List[Dict[str, Any]]
    ) -> Tuple[int, int, int]:
        """
        Process a single batch of products with bulk upsert.

        Uses ON CONFLICT DO UPDATE for upsert behavior.

        Returns:
            Tuple of (created_count, updated_count, failed_count)
        """
        if not products:
            return (0, 0, 0)

        product_records = []
        variant_records = []

        for product in products:
            product_data = await self._prepare_product_record(product)
            product_records.append(product_data)

            for variant_data in product.get("variants", []):
                variant_record = self._prepare_variant_record(
                    variant_data, product["external_product_id"]
                )
                variant_records.append(variant_record)

        created_count = 0
        updated_count = 0
        failed_count = 0

        try:
            if product_records:
                created, updated = await self._bulk_upsert_products(product_records)
                created_count += created
                updated_count += updated

            if variant_records:
                created_v, updated_v = await self._bulk_upsert_variants(variant_records)
                created_count += created_v
                updated_count += updated_v

        except Exception as e:
            logger.error("batch_upsert_failed", error=str(e))
            failed_count = len(products)
            raise

        return (created_count, updated_count, failed_count)

    async def _prepare_product_record(self, product: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare product record for database insert."""
        shop_id = await self._get_shop_id()
        return {
            "shop_id": shop_id,
            "external_product_id": product["external_product_id"],
            "title": product["title"],
            "description": product.get("description"),
            "status": product.get("status", "active"),
            "has_variants": product.get("has_variants", False),
            "raw_payload": product.get("raw_payload"),
            "moderation_status": product.get("moderation_status"),
            "last_synced_at": datetime.utcnow(),
        }

    def _prepare_variant_record(
        self, variant: Dict[str, Any], product_id: str
    ) -> Dict[str, Any]:
        """Prepare variant record for database insert."""
        return {
            "external_variant_id": variant["external_variant_id"],
            "external_product_id": product_id,
            "sku": variant.get("sku"),
            "attributes": variant.get("attributes", {}),
            "cost_price": variant.get("cost_price", 0),
            "inventory": variant.get("inventory", 0),
            "status": variant.get("status", "active"),
            "raw_payload": variant.get("raw_payload"),
        }

    async def _get_shop_id(self) -> UUID:
        """Get shop ID from integration."""
        await self._ensure_integration_loaded()
        if self._shop_id is None:
            raise ValueError(
                f"Integration {self.integration_id} not found or has no shop"
            )
        return self._shop_id

    async def _bulk_upsert_products(
        self, products: List[Dict[str, Any]]
    ) -> Tuple[int, int]:
        """
        Bulk upsert products using ON CONFLICT DO UPDATE.

        Returns:
            Tuple of (created_count, updated_count)
        """
        if not products:
            return (0, 0)

        stmt = pg_insert(SupplierProduct).values(products)

        stmt = stmt.on_conflict_do_update(
            index_elements=["external_product_id"],
            set_={
                "title": stmt.excluded.title,
                "description": stmt.excluded.description,
                "status": stmt.excluded.status,
                "has_variants": stmt.excluded.has_variants,
                "raw_payload": stmt.excluded.raw_payload,
                "moderation_status": stmt.excluded.moderation_status,
                "last_synced_at": stmt.excluded.last_synced_at,
                "updated_at": datetime.utcnow(),
            },
        )

        await self.session.execute(stmt)
        await self.session.flush()

        created = sum(1 for p in products if p.get("is_new", True))
        updated = len(products) - created

        return (created, updated)

    async def _bulk_upsert_variants(
        self, variants: List[Dict[str, Any]]
    ) -> Tuple[int, int]:
        """
        Bulk upsert variants using ON CONFLICT DO UPDATE.

        This is more complex as it requires:
        1. First ensuring ProductVariant exists
        2. Then upserting SupplierVariant with the ProductVariant reference

        Returns:
            Tuple of (created_count, updated_count)
        """
        if not variants:
            return (0, 0)

        product_variant_map: Dict[str, str] = {}

        for variant in variants:
            product_id = variant["external_product_id"]
            if product_id not in product_variant_map:
                product_result = await self.session.execute(
                    select(SupplierProduct.id).where(
                        SupplierProduct.external_product_id == product_id
                    )
                )
                product = product_result.scalar_one_or_none()
                if product:
                    product_variant_map[product_id] = str(product.id)

        variant_records = []
        for variant in variants:
            product_internal_id = product_variant_map.get(
                variant["external_product_id"]
            )
            if product_internal_id:
                variant_records.append(
                    {
                        "supplier_product_id": product_internal_id,
                        "external_variant_id": variant["external_variant_id"],
                        "sku": variant.get("sku"),
                        "attributes": variant.get("attributes", {}),
                        "cost_price": variant.get("cost_price", 0),
                        "inventory": variant.get("inventory", 0),
                        "status": variant.get("status", "active"),
                        "raw_payload": variant.get("raw_payload"),
                    }
                )

        if not variant_records:
            return (0, 0)

        stmt = pg_insert(SupplierVariant).values(variant_records)

        stmt = stmt.on_conflict_do_update(
            index_elements=["supplier_product_id", "external_variant_id"],
            set_={
                "sku": stmt.excluded.sku,
                "attributes": stmt.excluded.attributes,
                "cost_price": stmt.excluded.cost_price,
                "inventory": stmt.excluded.inventory,
                "status": stmt.excluded.status,
                "raw_payload": stmt.excluded.raw_payload,
                "updated_at": datetime.utcnow(),
            },
        )

        await self.session.execute(stmt)
        await self.session.flush()

        return (0, len(variant_records))

    async def _handle_forbidden_product(self, error: ForbiddenProductError) -> None:
        """
        Handle a forbidden product by updating its status and notifying affected sellers.

        When Basalam returns 403 for a product, we:
        1. Update the SupplierProduct status to 'forbidden'
        2. Record the validation error in basalam_validation_error JSONB
        3. Notify all sellers who have listed this product
        """
        product_id = error.product_id
        if not product_id:
            logger.warning("ForbiddenProductError without product_id, skipping")
            return

        # Find and update the supplier product
        stmt = (
            update(SupplierProduct)
            .where(SupplierProduct.external_product_id == str(product_id))
            .values(
                status="forbidden",
                basalam_validation_error={
                    "reason": error.reason or "forbidden_product",
                    "detected_at": datetime.utcnow().isoformat(),
                    "error_message": str(error),
                },
            )
        )
        await self.session.execute(stmt)
        await self.session.commit()

        logger.info("product_status_updated_to_forbidden", product_id=str(product_id))

        # Notify sellers with affected listings
        await self._notify_sellers_for_forbidden_product(str(product_id), error)

    async def _notify_sellers_for_forbidden_product(
        self, external_product_id: str, error: ForbiddenProductError
    ) -> None:
        """Notify all sellers who listed a forbidden product."""
        from src.domains.products.models import SellerListing
        from src.integrations.notification.manager import NotificationManager
        from src.integrations.notification.ports import NotificationRecipient

        # Find the supplier product
        product_stmt = select(SupplierProduct.id).where(
            SupplierProduct.external_product_id == external_product_id
        )
        product_result = await self.session.execute(product_stmt)
        supplier_product_id = product_result.scalar_one_or_none()

        if not supplier_product_id:
            return

        # Find all active seller listings for this product
        listings_stmt = select(SellerListing).where(
            and_(
                SellerListing.supplier_product_id == supplier_product_id,
                SellerListing.sync_enabled == True,
            )
        )
        listings_result = await self.session.execute(listings_stmt)
        listings = listings_result.fetchall()

        if not listings:
            return

        notification_manager = NotificationManager()

        for listing in listings:
            try:
                recipient = NotificationRecipient(
                    user_id=listing.shop_id,
                )
                await notification_manager.notify_event(
                    event_type="product_forbidden",
                    recipient=recipient,
                    event_data={
                        "product_id": str(listing.id),
                        "external_product_id": external_product_id,
                        "product_title": listing.custom_title or "",
                        "reason": error.reason or "Product rejected by Basalam",
                        "action": "This product has been removed from sale. Please review and remove it from your store.",
                    },
                )
                logger.info("notified_seller_about_forbidden_product", shop_id=str(listing.shop_id), external_product_id=external_product_id)
            except Exception as notify_err:
                logger.error("failed_to_notify_seller", shop_id=str(listing.shop_id), error=str(notify_err))

    async def get_sync_status(self) -> Dict[str, Any]:
        """Get current sync status for this integration."""
        sync_state = await self._get_or_create_sync_state("product")

        return {
            "integration_id": str(self.integration_id),
            "sync_mode": sync_state.sync_mode,
            "status": sync_state.status,
            "last_sync_timestamp": sync_state.last_sync_timestamp.isoformat()
            if sync_state.last_sync_timestamp
            else None,
            "cursor_token": sync_state.cursor_token,
            "total_synced": sync_state.total_synced,
            "created_count": sync_state.created_count,
            "updated_count": sync_state.updated_count,
            "failed_count": sync_state.failed_count,
            "last_error": sync_state.last_error,
        }

    async def reset_sync_state(self) -> None:
        """Reset sync state to allow full resync."""
        sync_state = await self._get_or_create_sync_state("product")
        sync_state.cursor_token = None
        sync_state.last_sync_timestamp = None
        sync_state.status = "idle"
        sync_state.total_synced = 0
        sync_state.created_count = 0
        sync_state.updated_count = 0
        sync_state.failed_count = 0
        sync_state.last_error = None
        await self.session.flush()

        logger.info("sync_state_reset", integration_id=str(self.integration_id))
