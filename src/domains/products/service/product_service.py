"""
Product Service
===============
Business logic for product and listing management.

Handles:
- Supplier product CRUD with domain events
- Seller listing management with price calculation
- Catalog browsing with filters
- Variant and media management
"""

import structlog
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models import (
    Category,
    ProductMedia,
    ProductVariant,
    SellerListing,
    SellerVariant,
    SupplierProduct,
    SupplierVariant,
)
from ..repository import (
    CategoryRepository,
    SellerListingRepository,
    SellerVariantRepository,
    SupplierProductRepository,
    SupplierVariantRepository,
)
from ..schemas import CatalogProductResponse, ProductMediaResponse, ProductStatus
from src.core.events.base import DomainEvent
from src.core.events.publisher import EventPublisher
from src.core.events.product import (
    ProductCreated,
    ProductUpdated,
    ProductStatusChanged,
)

logger = structlog.get_logger(__name__)


def calculate_listing_price(supplier_cost: Decimal, margin_percent: Decimal) -> Decimal:
    """Calculate seller listing price: supplier_cost * (1 + margin_percent / 100)."""
    return supplier_cost * (1 + margin_percent / Decimal("100"))


class ProductService:
    """
    Service for managing products and seller listings.

    Delegates persistence to repositories and publishes domain events
    for cross-bounded-context integration.
    """

    def __init__(
        self,
        session: AsyncSession,
        event_publisher: Optional[EventPublisher] = None,
    ):
        self.session = session
        self._event_publisher = event_publisher
        self._product_repo = SupplierProductRepository(session)
        self._listing_repo = SellerListingRepository(session)
        self._supplier_variant_repo = SupplierVariantRepository(session)
        self._seller_variant_repo = SellerVariantRepository(session)
        self._category_repo = CategoryRepository(session)

    async def _publish_event(self, event: DomainEvent) -> None:
        """Safely publish domain event. Non-blocking -- failures are logged but don't raise."""
        if self._event_publisher is None:
            return
        try:
            await self._event_publisher.publish(topic="events", event=event)
        except Exception as e:
            logger.warning(
                "failed_to_publish_event",
                event_type=event.event_type,
                error=str(e),
            )

    # -------------------------------------------------------
    # Category
    # -------------------------------------------------------

    async def list_categories(
        self,
        parent_id: Optional[UUID] = None,
        is_active: Optional[bool] = True,
    ) -> List[Category]:
        """List categories with optional parent and active-status filters."""
        stmt = select(Category)
        if parent_id is not None:
            stmt = stmt.where(Category.parent_id == parent_id)
        if is_active is not None:
            stmt = stmt.where(Category.is_active == is_active)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_category(self, category_id: UUID) -> Optional[Category]:
        """Get category by ID."""
        return await self._category_repo.get_by_id(category_id)

    async def create_category(self, data: dict) -> Category:
        """Create a new category."""
        return await self._category_repo.create(data)

    # -------------------------------------------------------
    # Supplier Products
    # -------------------------------------------------------

    async def list_products(
        self,
        *,
        shop_id: Optional[UUID] = None,
        category_id: Optional[UUID] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
        user_shop_ids: Optional[List[UUID]] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[SupplierProduct]:
        """
        List supplier products with filters.

        When *user_shop_ids* is provided (non-admin users), results are
        scoped to products belonging to those shops.
        """
        stmt = select(SupplierProduct)

        if shop_id:
            stmt = stmt.where(SupplierProduct.shop_id == shop_id)
        elif user_shop_ids is not None:
            stmt = stmt.where(SupplierProduct.shop_id.in_(user_shop_ids))

        if category_id:
            stmt = stmt.where(SupplierProduct.category_id == category_id)
        if status:
            stmt = stmt.where(SupplierProduct.status == status)
        if search:
            escaped = search.replace("%", "\\%").replace("_", "\\_")
            stmt = stmt.where(SupplierProduct.title.ilike(f"%{escaped}%"))

        stmt = (
            stmt.limit(limit).offset(offset).order_by(SupplierProduct.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_product(self, product_id: UUID) -> Optional[SupplierProduct]:
        """Get product by ID with eager-loaded relations."""
        result = await self.session.execute(
            select(SupplierProduct)
            .where(SupplierProduct.id == product_id)
            .options(
                selectinload(SupplierProduct.variants),
                selectinload(SupplierProduct.images),
                selectinload(SupplierProduct.seller_listings),
            )
        )
        return result.scalar_one_or_none()

    async def get_product_raw(self, product_id: UUID) -> Optional[SupplierProduct]:
        """Get product by ID without eager loading (lighter query)."""
        return await self._product_repo.get_by_id(product_id)

    async def create_product(self, data: dict) -> SupplierProduct:
        """Create a new supplier product and publish ProductCreated event."""
        product = await self._product_repo.create(data)

        event = ProductCreated(
            product_id=product.id,
            shop_id=product.shop_id,
            title=product.title,
        )
        await self._publish_event(event)

        return product

    async def update_product(
        self, product_id: UUID, data: dict
    ) -> Optional[SupplierProduct]:
        """Update a product and publish ProductUpdated event."""
        product = await self._product_repo.update(product_id, data)
        if not product:
            return None

        event = ProductUpdated(
            product_id=product_id,
            changes=data,
        )
        await self._publish_event(event)

        return product

    async def delete_product(self, product_id: UUID) -> bool:
        """Soft-delete a product (sets status to archived) and publish events."""
        product = await self._product_repo.get_by_id(product_id)
        if not product:
            return False

        old_status = product.status
        success = await self._product_repo.delete(product_id)
        if success:
            event = ProductStatusChanged(
                product_id=product_id,
                old_status=old_status,
                new_status=ProductStatus.ARCHIVED.value,
            )
            await self._publish_event(event)
        return success

    # -------------------------------------------------------
    # Catalog
    # -------------------------------------------------------

    async def browse_catalog(
        self,
        *,
        category_id: Optional[UUID] = None,
        min_price: Optional[Decimal] = None,
        max_price: Optional[Decimal] = None,
        in_stock_only: bool = False,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[CatalogProductResponse]:
        """
        Browse active seller listings as catalog items.

        Returns typed CatalogProductResponse objects validated via Pydantic.
        """
        stmt = (
            select(SellerListing)
            .where(SellerListing.status == "active")
            .options(
                selectinload(SellerListing.supplier_product),
                selectinload(SellerListing.variants),
            )
        )

        if category_id:
            stmt = stmt.join(SupplierProduct).where(
                SupplierProduct.category_id == category_id
            )
        if search:
            escaped = search.replace("%", "\\%").replace("_", "\\_")
            stmt = stmt.join(SupplierProduct).where(
                SupplierProduct.title.ilike(f"%{escaped}%")
            )

        stmt = stmt.limit(limit).offset(offset)

        result = await self.session.execute(stmt)
        listings = result.scalars().all()

        catalog_items: List[CatalogProductResponse] = []
        for listing in listings:
            product = listing.supplier_product
            variants = listing.variants

            prices = [v.price for v in variants if v.price]
            min_price_val = min(prices) if prices else Decimal("0")
            max_price_val = max(prices) if prices else Decimal("0")

            in_stock = any(
                v.inventory_cache and v.inventory_cache > 0 for v in variants
            )

            if in_stock_only and not in_stock:
                continue
            if min_price is not None and min_price_val < min_price:
                continue
            if max_price is not None and max_price_val > max_price:
                continue

            catalog_items.append(
                CatalogProductResponse(
                    id=listing.id,
                    title=listing.custom_title or product.title,
                    description=listing.custom_description or product.description,
                    min_price=min_price_val,
                    max_price=max_price_val,
                    has_variants=product.has_variants,
                    images=[
                        ProductMediaResponse.model_validate(m) for m in product.images
                    ],
                    available=in_stock,
                )
            )

        return catalog_items

    # -------------------------------------------------------
    # Seller Listings
    # -------------------------------------------------------

    async def create_listing(
        self,
        shop_id: UUID,
        supplier_product_id: UUID,
        margin_percent: Decimal,
        sync_enabled: bool = True,
        sync_price: bool = True,
        sync_inventory: bool = True,
    ) -> SellerListing:
        """
        Create a seller listing from a supplier product.

        For each supplier variant, creates a SellerVariant with the
        calculated listing price (supplier_cost * (1 + margin/100)).
        """
        product = await self._product_repo.get_by_id(supplier_product_id)
        if not product:
            raise ValueError("Supplier product not found")

        listing = await self._listing_repo.create(
            {
                "shop_id": shop_id,
                "supplier_product_id": supplier_product_id,
                "margin_percent": margin_percent,
                "sync_enabled": sync_enabled,
                "sync_price": sync_price,
                "sync_inventory": sync_inventory,
            }
        )

        # Fetch supplier variants for the product to build seller variants.
        result = await self.session.execute(
            select(SupplierVariant).where(
                SupplierVariant.supplier_product_id == supplier_product_id
            )
        )
        supplier_variants = result.scalars().all()

        for sv in supplier_variants:
            listing_price = calculate_listing_price(sv.cost_price, margin_percent)
            await self._seller_variant_repo.create(
                {
                    "listing_id": listing.id,
                    "supplier_variant_id": sv.id,
                    "price": listing_price,
                    "inventory_cache": sv.inventory,
                }
            )

        await self.session.flush()
        await self.session.refresh(listing)
        return listing

    async def get_listing(self, listing_id: UUID) -> Optional[SellerListing]:
        """Get listing by ID."""
        return await self._listing_repo.get_by_id(listing_id)

    async def update_listing(
        self, listing_id: UUID, data: dict
    ) -> Optional[SellerListing]:
        """Update a seller listing."""
        return await self._listing_repo.update(listing_id, data)

    async def delete_listing(self, listing_id: UUID) -> bool:
        """Soft-delete a listing (sets status to disabled)."""
        return await self._listing_repo.delete(listing_id)

    # -------------------------------------------------------
    # Product Variants
    # -------------------------------------------------------

    async def list_variants(self, product_id: UUID) -> List[ProductVariant]:
        """List variants for a product."""
        result = await self.session.execute(
            select(ProductVariant).where(ProductVariant.product_id == product_id)
        )
        return list(result.scalars().all())

    async def create_variant(self, product_id: UUID, data: dict) -> ProductVariant:
        """Create a product variant."""
        variant = ProductVariant(product_id=product_id, **data)
        self.session.add(variant)
        await self.session.flush()
        await self.session.refresh(variant)
        return variant

    async def get_variant(self, variant_id: UUID) -> Optional[ProductVariant]:
        """Get variant by ID."""
        result = await self.session.execute(
            select(ProductVariant).where(ProductVariant.id == variant_id)
        )
        return result.scalar_one_or_none()

    # -------------------------------------------------------
    # Supplier Variants
    # -------------------------------------------------------

    async def get_supplier_variant_by_variant(
        self, variant_id: UUID
    ) -> Optional[SupplierVariant]:
        """Get supplier variant by base variant ID."""
        result = await self.session.execute(
            select(SupplierVariant).where(SupplierVariant.variant_id == variant_id)
        )
        return result.scalar_one_or_none()

    # -------------------------------------------------------
    # Seller Variants
    # -------------------------------------------------------

    async def list_seller_variants(self, listing_id: UUID) -> List[SellerVariant]:
        """List seller variants for a listing."""
        return await self._seller_variant_repo.get_by_listing(listing_id)

    async def update_seller_variant(
        self,
        listing_id: UUID,
        variant_id: UUID,
        data: dict,
    ) -> Optional[SellerVariant]:
        """Update seller variant price or enabled status."""
        result = await self.session.execute(
            select(SellerVariant).where(
                SellerVariant.id == variant_id,
                SellerVariant.listing_id == listing_id,
            )
        )
        variant = result.scalar_one_or_none()
        if not variant:
            return None

        allowed_fields = {"price", "inventory_cache", "custom_price", "is_enabled"}
        disallowed = set(data.keys()) - allowed_fields
        if disallowed:
            raise ValueError(
                f"Cannot update fields: {', '.join(sorted(disallowed))}. "
                f"Allowed fields: {', '.join(sorted(allowed_fields))}."
            )
        for key, value in data.items():
            setattr(variant, key, value)
        await self.session.flush()
        await self.session.refresh(variant)
        return variant

    # -------------------------------------------------------
    # Product Media
    # -------------------------------------------------------

    async def list_product_media(self, product_id: UUID) -> List[ProductMedia]:
        """List media for a product, ordered by sort_order."""
        result = await self.session.execute(
            select(ProductMedia)
            .where(ProductMedia.product_id == product_id)
            .order_by(ProductMedia.sort_order)
        )
        return list(result.scalars().all())

    async def add_product_media(self, product_id: UUID, data: dict) -> ProductMedia:
        """Add media to a product."""
        media = ProductMedia(product_id=product_id, **data)
        self.session.add(media)
        await self.session.flush()
        await self.session.refresh(media)
        return media

    async def get_media(self, media_id: UUID) -> Optional[ProductMedia]:
        """Get media by ID."""
        result = await self.session.execute(
            select(ProductMedia).where(ProductMedia.id == media_id)
        )
        return result.scalar_one_or_none()

    async def delete_media(self, media_id: UUID) -> bool:
        """Delete a media record."""
        media = await self.get_media(media_id)
        if not media:
            return False
        await self.session.delete(media)
        await self.session.flush()
        return True

    # -------------------------------------------------------
    # Bulk Import
    # -------------------------------------------------------

    async def bulk_import_products(
        self, products_data: List[dict]
    ) -> List[SupplierProduct]:
        """
        Bulk-import supplier products.

        Creates each product via the repository and publishes a
        ProductCreated event per product.
        """
        created: List[SupplierProduct] = []
        for data in products_data:
            product = await self._product_repo.create(data)

            event = ProductCreated(
                product_id=product.id,
                shop_id=product.shop_id,
                title=product.title,
            )
            await self._publish_event(event)
            created.append(product)

        return created
