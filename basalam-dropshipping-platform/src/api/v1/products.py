"""
Products API Endpoints
======================
FastAPI endpoints for product management
"""

from uuid import UUID
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, model_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.api.deps import get_db, get_current_user, check_shop_access, is_admin
from src.domains.accounts.models import User
from src.domains.shops.models import Shop
from src.domains.accounts.models import Account
from src.domains.products.models import (
    SupplierProduct,
    ProductVariant,
    SupplierVariant,
    SellerListing,
    SellerVariant,
    ProductMedia,
    Category,
)
from src.domains.products.schemas import (
    SupplierProductResponse,
    SupplierProductCreate,
    SupplierProductUpdate,
    ProductVariantResponse,
    SupplierVariantResponse,
    SellerListingResponse,
    SellerListingCreate,
    SellerListingUpdate,
    SellerVariantResponse,
    SellerVariantBase,
    CategoryResponse,
    CategoryBase,
    ProductMediaResponse,
    ProductMediaBase,
    ProductStatus,
)


class ProductVariantCreateRequest(BaseModel):
    """Schema for creating a product variant"""
    sku: Optional[str] = None
    external_variant_id: Optional[str] = None
    attributes: Optional[dict] = None

    @model_validator(mode='after')
    def check_at_least_one_id(self):
        if not self.sku and not self.external_variant_id:
            raise ValueError('At least one of sku or external_variant_id is required')
        return self


# ============================================
# API Router
# ============================================

router = APIRouter(prefix="/products", tags=["products"])


# ---- Category Endpoints ----


@router.get("/categories", response_model=List[CategoryResponse])
async def list_categories(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    parent_id: Optional[UUID] = None,
    is_active: Optional[bool] = True,
):
    """List product categories"""
    query = select(Category)
    if parent_id is not None:
        query = query.where(Category.parent_id == parent_id)
    if is_active is not None:
        query = query.where(Category.is_active == is_active)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/categories/{category_id}", response_model=CategoryResponse)
async def get_category(category_id: UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Get category by ID"""
    result = await db.execute(select(Category).where(Category.id == category_id))
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    return category


@router.post(
    "/categories", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED
)
async def create_category(
    category_data: CategoryBase, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Create a new category"""
    category = Category(**category_data.model_dump())
    db.add(category)
    await db.flush()
    await db.refresh(category)
    return category


# ---- Supplier Product Endpoints ----


@router.post(
    "/", response_model=SupplierProductResponse, status_code=status.HTTP_201_CREATED
)
async def create_product(
    product_data: SupplierProductCreate, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Create a new supplier product"""
    await check_shop_access(db, product_data.shop_id, current_user)
    product = SupplierProduct(**product_data.model_dump())
    db.add(product)
    await db.flush()
    await db.refresh(product)
    return product


@router.get("/", response_model=List[SupplierProductResponse])
async def list_products(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    shop_id: Optional[UUID] = None,
    category_id: Optional[UUID] = None,
    status: Optional[ProductStatus] = None,
    search: Optional[str] = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List supplier products with filters. Scoped to user's shops unless admin."""
    if shop_id:
        await check_shop_access(db, shop_id, current_user)

    query = select(SupplierProduct)

    if shop_id:
        query = query.where(SupplierProduct.shop_id == shop_id)
    elif not is_admin(current_user):
        # Scope to products belonging to user's shops
        user_shops = (
            select(Shop.id)
            .join(Account, Shop.account_id == Account.id)
            .where(Account.owner_user_id == current_user.id)
        )
        query = query.where(SupplierProduct.shop_id.in_(user_shops))
    if category_id:
        query = query.where(SupplierProduct.category_id == category_id)
    if status:
        query = query.where(SupplierProduct.status == status.value)
    if search:
        escaped_search = search.replace("%", "\\%").replace("_", "\\_")
        query = query.where(SupplierProduct.title.ilike(f"%{escaped_search}%"))

    query = (
        query.limit(limit).offset(offset).order_by(SupplierProduct.created_at.desc())
    )

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/catalog", response_model=List[dict])
async def browse_catalog(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    category_id: Optional[UUID] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    in_stock_only: bool = False,
    search: Optional[str] = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Browse product catalog (for sellers)"""
    query = (
        select(SellerListing)
        .where(SellerListing.status == "active")
        .options(
            selectinload(SellerListing.supplier_product),
            selectinload(SellerListing.variants),
        )
    )

    if category_id:
        query = query.join(SupplierProduct).where(
            SupplierProduct.category_id == category_id
        )
    if search:
        escaped_search = search.replace("%", "\\%").replace("_", "\\_")
        query = query.join(SupplierProduct).where(
            SupplierProduct.title.ilike(f"%{escaped_search}%")
        )

    query = query.limit(limit).offset(offset)

    result = await db.execute(query)
    listings = result.scalars().all()

    catalog_items = []
    for listing in listings:
        product = listing.supplier_product
        variants = listing.variants

        prices = [v.price for v in variants if v.price]
        min_price_val = min(prices) if prices else 0
        max_price_val = max(prices) if prices else 0

        in_stock = any(v.inventory_cache and v.inventory_cache > 0 for v in variants)

        if in_stock_only and not in_stock:
            continue
        if min_price and min_price_val < min_price:
            continue
        if max_price and max_price_val > max_price:
            continue

        catalog_items.append(
            {
                "id": listing.id,
                "title": listing.custom_title or product.title,
                "description": listing.custom_description or product.description,
                "min_price": min_price_val,
                "max_price": max_price_val,
                "has_variants": product.has_variants,
                "images": [{"url": m.url} for m in product.images],
                "available": in_stock,
            }
        )

    return catalog_items


@router.get("/{product_id}", response_model=SupplierProductResponse)
async def get_product(product_id: UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Get product by ID (requires authentication, not ownership)"""
    result = await db.execute(
        select(SupplierProduct)
        .where(SupplierProduct.id == product_id)
        .options(
            selectinload(SupplierProduct.variants),
            selectinload(SupplierProduct.images),
            selectinload(SupplierProduct.seller_listings),
        )
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.patch("/{product_id}", response_model=SupplierProductResponse)
async def update_product(
    product_id: UUID,
    product_data: SupplierProductUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a product"""
    result = await db.execute(
        select(SupplierProduct).where(SupplierProduct.id == product_id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    await check_shop_access(db, product.shop_id, current_user)

    update_dict = product_data.model_dump(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(product, field, value)

    await db.flush()
    await db.refresh(product)
    return product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(product_id: UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Delete a product (soft delete by setting status to archived)"""
    result = await db.execute(
        select(SupplierProduct).where(SupplierProduct.id == product_id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    await check_shop_access(db, product.shop_id, current_user)

    product.status = ProductStatus.ARCHIVED.value
    await db.flush()


# ---- Product Variant Endpoints ----


@router.get("/{product_id}/variants", response_model=List[ProductVariantResponse])
async def list_variants(product_id: UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """List variants for a product"""
    product_result = await db.execute(
        select(SupplierProduct).where(SupplierProduct.id == product_id)
    )
    product = product_result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    await check_shop_access(db, product.shop_id, current_user)

    result = await db.execute(
        select(ProductVariant).where(ProductVariant.product_id == product_id)
    )
    return result.scalars().all()


@router.post(
    "/{product_id}/variants",
    response_model=ProductVariantResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_variant(
    product_id: UUID, variant_data: ProductVariantCreateRequest, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Create a product variant"""
    product_result = await db.execute(
        select(SupplierProduct).where(SupplierProduct.id == product_id)
    )
    product = product_result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    await check_shop_access(db, product.shop_id, current_user)

    variant = ProductVariant(product_id=product_id, **variant_data.model_dump(exclude_unset=True))
    db.add(variant)
    await db.flush()
    await db.refresh(variant)
    return variant


@router.get("/variants/{variant_id}", response_model=ProductVariantResponse)
async def get_variant(variant_id: UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Get variant by ID"""
    result = await db.execute(
        select(ProductVariant).where(ProductVariant.id == variant_id)
    )
    variant = result.scalar_one_or_none()
    if not variant:
        raise HTTPException(status_code=404, detail="Variant not found")
    # Verify ownership via the parent product — parent must exist
    product_result = await db.execute(
        select(SupplierProduct).where(SupplierProduct.id == variant.product_id)
    )
    product = product_result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Parent product not found")
    await check_shop_access(db, product.shop_id, current_user)
    return variant


# ---- Supplier Variant Endpoints ----


@router.get("/variants/{variant_id}/supplier", response_model=SupplierVariantResponse)
async def get_supplier_variant(variant_id: UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Get supplier variant details (price, inventory)"""
    result = await db.execute(
        select(SupplierVariant).where(SupplierVariant.variant_id == variant_id)
    )
    variant = result.scalar_one_or_none()
    if not variant:
        raise HTTPException(status_code=404, detail="Supplier variant not found")
    # Verify ownership via the parent product — parent must exist
    product_result = await db.execute(
        select(SupplierProduct).where(SupplierProduct.id == variant.supplier_product_id)
    )
    product = product_result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Parent product not found")
    await check_shop_access(db, product.shop_id, current_user)
    return variant


# ---- Seller Listing Endpoints ----


@router.post(
    "/listings",
    response_model=SellerListingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_listing(
    listing_data: SellerListingCreate, shop_id: UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Create a seller listing from a supplier product"""
    await check_shop_access(db, shop_id, current_user)

    result = await db.execute(
        select(SupplierProduct).where(
            SupplierProduct.id == listing_data.supplier_product_id
        )
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Supplier product not found")

    listing = SellerListing(shop_id=shop_id, **listing_data.model_dump())
    db.add(listing)

    for variant in product.variants:
        seller_variant = SellerVariant(
            listing_id=listing.id,
            supplier_variant_id=variant.supplier_variants[0].id
            if variant.supplier_variants
            else None,
            price=variant.supplier_variants[0].cost_price
            * (1 + listing_data.margin_percent / 100)
            if variant.supplier_variants
            else 0,
            inventory_cache=variant.supplier_variants[0].inventory
            if variant.supplier_variants
            else 0,
        )
        db.add(seller_variant)

    await db.flush()
    await db.refresh(listing)
    return listing


@router.get("/listings/{listing_id}", response_model=SellerListingResponse)
async def get_listing(listing_id: UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Get seller listing by ID"""
    result = await db.execute(
        select(SellerListing).where(SellerListing.id == listing_id)
    )
    listing = result.scalar_one_or_none()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    await check_shop_access(db, listing.shop_id, current_user)
    return listing


@router.patch("/listings/{listing_id}", response_model=SellerListingResponse)
async def update_listing(
    listing_id: UUID,
    listing_data: SellerListingUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a seller listing"""
    result = await db.execute(
        select(SellerListing).where(SellerListing.id == listing_id)
    )
    listing = result.scalar_one_or_none()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    await check_shop_access(db, listing.shop_id, current_user)

    update_dict = listing_data.model_dump(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(listing, field, value)

    await db.flush()
    await db.refresh(listing)
    return listing


@router.delete("/listings/{listing_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_listing(listing_id: UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Delete a seller listing"""
    result = await db.execute(
        select(SellerListing).where(SellerListing.id == listing_id)
    )
    listing = result.scalar_one_or_none()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    await check_shop_access(db, listing.shop_id, current_user)

    listing.status = "disabled"
    await db.flush()


# ---- Seller Variant Endpoints ----


@router.get(
    "/listings/{listing_id}/variants", response_model=List[SellerVariantResponse]
)
async def list_seller_variants(listing_id: UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """List seller variants for a listing"""
    listing_result = await db.execute(
        select(SellerListing).where(SellerListing.id == listing_id)
    )
    listing = listing_result.scalar_one_or_none()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    await check_shop_access(db, listing.shop_id, current_user)

    result = await db.execute(
        select(SellerVariant).where(SellerVariant.listing_id == listing_id)
    )
    return result.scalars().all()


@router.patch(
    "/listings/{listing_id}/variants/{variant_id}", response_model=SellerVariantResponse
)
async def update_seller_variant(
    listing_id: UUID,
    variant_id: UUID,
    variant_data: SellerVariantBase,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update seller variant price or enabled status"""
    # First verify the listing belongs to the user
    listing_result = await db.execute(
        select(SellerListing).where(SellerListing.id == listing_id)
    )
    listing = listing_result.scalar_one_or_none()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    await check_shop_access(db, listing.shop_id, current_user)

    result = await db.execute(
        select(SellerVariant).where(
            SellerVariant.id == variant_id, SellerVariant.listing_id == listing_id
        )
    )
    variant = result.scalar_one_or_none()
    if not variant:
        raise HTTPException(status_code=404, detail="Variant not found")

    update_dict = variant_data.model_dump(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(variant, field, value)

    await db.flush()
    await db.refresh(variant)
    return variant


# ---- Product Media Endpoints ----


@router.get("/{product_id}/media", response_model=List[ProductMediaResponse])
async def list_product_media(product_id: UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """List media for a product"""
    product_result = await db.execute(
        select(SupplierProduct).where(SupplierProduct.id == product_id)
    )
    product = product_result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    await check_shop_access(db, product.shop_id, current_user)

    result = await db.execute(
        select(ProductMedia)
        .where(ProductMedia.product_id == product_id)
        .order_by(ProductMedia.sort_order)
    )
    return result.scalars().all()


@router.post(
    "/{product_id}/media",
    response_model=ProductMediaResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_product_media(
    product_id: UUID, media_data: ProductMediaBase, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Add media to a product"""
    product_result = await db.execute(
        select(SupplierProduct).where(SupplierProduct.id == product_id)
    )
    product = product_result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    await check_shop_access(db, product.shop_id, current_user)

    media = ProductMedia(product_id=product_id, **media_data.model_dump())
    db.add(media)
    await db.flush()
    await db.refresh(media)
    return media


@router.delete("/media/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product_media(media_id: UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Delete product media"""
    result = await db.execute(select(ProductMedia).where(ProductMedia.id == media_id))
    media = result.scalar_one_or_none()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    # Verify ownership via the parent product — parent must exist
    product_result = await db.execute(
        select(SupplierProduct).where(SupplierProduct.id == media.product_id)
    )
    product = product_result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Parent product not found")
    await check_shop_access(db, product.shop_id, current_user)

    await db.delete(media)
    await db.flush()
