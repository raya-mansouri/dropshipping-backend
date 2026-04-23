"""
Products API Endpoints
======================
FastAPI endpoints for product management

All business logic is delegated to ProductService.
"""

from uuid import UUID
from typing import List, Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, model_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.api.deps import (
    get_db,
    get_current_user,
    get_product_service,
    check_shop_access,
    is_admin,
)
from src.domains.accounts.models import User
from src.domains.shops.models import Shop
from src.domains.accounts.models import Account
from src.domains.products.schemas import (
    CatalogProductResponse,
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
from src.domains.products.service.product_service import ProductService


class ProductVariantCreateRequest(BaseModel):
    """Schema for creating a product variant"""

    sku: Optional[str] = None
    external_variant_id: Optional[str] = None
    attributes: Optional[dict] = None

    @model_validator(mode="after")
    def check_at_least_one_id(self):
        if not self.sku and not self.external_variant_id:
            raise ValueError("At least one of sku or external_variant_id is required")
        return self


# ============================================
# API Router
# ============================================

router = APIRouter(prefix="/products", tags=["products"])


# ---- Category Endpoints ----


@router.get("/categories", response_model=List[CategoryResponse])
async def list_categories(
    current_user: User = Depends(get_current_user),
    service: ProductService = Depends(get_product_service),
    parent_id: Optional[UUID] = None,
    is_active: Optional[bool] = True,
):
    """List product categories"""
    return await service.list_categories(parent_id=parent_id, is_active=is_active)


@router.get("/categories/{category_id}", response_model=CategoryResponse)
async def get_category(
    category_id: UUID,
    current_user: User = Depends(get_current_user),
    service: ProductService = Depends(get_product_service),
):
    """Get category by ID"""
    category = await service.get_category(category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    return category


@router.post(
    "/categories", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED
)
async def create_category(
    category_data: CategoryBase,
    current_user: User = Depends(get_current_user),
    service: ProductService = Depends(get_product_service),
):
    """Create a new category"""
    return await service.create_category(category_data.model_dump())


# ---- Supplier Product Endpoints ----


@router.post(
    "/", response_model=SupplierProductResponse, status_code=status.HTTP_201_CREATED
)
async def create_product(
    product_data: SupplierProductCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: ProductService = Depends(get_product_service),
):
    """Create a new supplier product"""
    await check_shop_access(db, product_data.shop_id, current_user)
    return await service.create_product(product_data.model_dump())


@router.get("/", response_model=List[SupplierProductResponse])
async def list_products(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: ProductService = Depends(get_product_service),
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

    user_shop_ids: Optional[List[UUID]] = None
    if not shop_id and not is_admin(current_user):
        result = await db.execute(
            select(Shop.id)
            .join(Account, Shop.account_id == Account.id)
            .where(Account.owner_user_id == current_user.id)
        )
        user_shop_ids = [row[0] for row in result.all()]

    return await service.list_products(
        shop_id=shop_id,
        category_id=category_id,
        status=status.value if status else None,
        search=search,
        user_shop_ids=user_shop_ids,
        limit=limit,
        offset=offset,
    )


@router.get("/catalog", response_model=List[CatalogProductResponse])
async def browse_catalog(
    current_user: User = Depends(get_current_user),
    service: ProductService = Depends(get_product_service),
    category_id: Optional[UUID] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    in_stock_only: bool = False,
    search: Optional[str] = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Browse product catalog (for sellers)"""
    return await service.browse_catalog(
        category_id=category_id,
        min_price=Decimal(str(min_price)) if min_price is not None else None,
        max_price=Decimal(str(max_price)) if max_price is not None else None,
        in_stock_only=in_stock_only,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.get("/{product_id}", response_model=SupplierProductResponse)
async def get_product(
    product_id: UUID,
    current_user: User = Depends(get_current_user),
    service: ProductService = Depends(get_product_service),
):
    """Get product by ID (requires authentication, not ownership)"""
    product = await service.get_product(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.patch("/{product_id}", response_model=SupplierProductResponse)
async def update_product(
    product_id: UUID,
    product_data: SupplierProductUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: ProductService = Depends(get_product_service),
):
    """Update a product"""
    product = await service.get_product_raw(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    await check_shop_access(db, product.shop_id, current_user)

    update_dict = product_data.model_dump(exclude_unset=True)
    updated = await service.update_product(product_id, update_dict)
    return updated


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: ProductService = Depends(get_product_service),
):
    """Delete a product (soft delete by setting status to archived)"""
    product = await service.get_product_raw(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    await check_shop_access(db, product.shop_id, current_user)

    await service.delete_product(product_id)


# ---- Product Variant Endpoints ----


@router.get("/{product_id}/variants", response_model=List[ProductVariantResponse])
async def list_variants(
    product_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: ProductService = Depends(get_product_service),
):
    """List variants for a product"""
    product = await service.get_product_raw(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    await check_shop_access(db, product.shop_id, current_user)

    return await service.list_variants(product_id)


@router.post(
    "/{product_id}/variants",
    response_model=ProductVariantResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_variant(
    product_id: UUID,
    variant_data: ProductVariantCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: ProductService = Depends(get_product_service),
):
    """Create a product variant"""
    product = await service.get_product_raw(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    await check_shop_access(db, product.shop_id, current_user)

    return await service.create_variant(
        product_id, variant_data.model_dump(exclude_unset=True)
    )


@router.get("/variants/{variant_id}", response_model=ProductVariantResponse)
async def get_variant(
    variant_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: ProductService = Depends(get_product_service),
):
    """Get variant by ID"""
    variant = await service.get_variant(variant_id)
    if not variant:
        raise HTTPException(status_code=404, detail="Variant not found")
    product = await service.get_product_raw(variant.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Parent product not found")
    await check_shop_access(db, product.shop_id, current_user)
    return variant


# ---- Supplier Variant Endpoints ----


@router.get("/variants/{variant_id}/supplier", response_model=SupplierVariantResponse)
async def get_supplier_variant(
    variant_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: ProductService = Depends(get_product_service),
):
    """Get supplier variant details (price, inventory)"""
    variant = await service.get_supplier_variant_by_variant(variant_id)
    if not variant:
        raise HTTPException(status_code=404, detail="Supplier variant not found")
    product = await service.get_product_raw(variant.supplier_product_id)
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
    listing_data: SellerListingCreate,
    shop_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: ProductService = Depends(get_product_service),
):
    """Create a seller listing from a supplier product"""
    await check_shop_access(db, shop_id, current_user)

    try:
        listing = await service.create_listing(
            shop_id=shop_id,
            supplier_product_id=listing_data.supplier_product_id,
            margin_percent=listing_data.margin_percent,
            sync_enabled=listing_data.sync_enabled,
            sync_price=listing_data.sync_price,
            sync_inventory=listing_data.sync_inventory,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return listing


@router.get("/listings/{listing_id}", response_model=SellerListingResponse)
async def get_listing(
    listing_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: ProductService = Depends(get_product_service),
):
    """Get seller listing by ID"""
    listing = await service.get_listing(listing_id)
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
    service: ProductService = Depends(get_product_service),
):
    """Update a seller listing"""
    listing = await service.get_listing(listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    await check_shop_access(db, listing.shop_id, current_user)

    update_dict = listing_data.model_dump(exclude_unset=True)
    updated = await service.update_listing(listing_id, update_dict)
    return updated


@router.delete("/listings/{listing_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_listing(
    listing_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: ProductService = Depends(get_product_service),
):
    """Delete a seller listing"""
    listing = await service.get_listing(listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    await check_shop_access(db, listing.shop_id, current_user)

    await service.delete_listing(listing_id)


# ---- Seller Variant Endpoints ----


@router.get(
    "/listings/{listing_id}/variants", response_model=List[SellerVariantResponse]
)
async def list_seller_variants(
    listing_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: ProductService = Depends(get_product_service),
):
    """List seller variants for a listing"""
    listing = await service.get_listing(listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    await check_shop_access(db, listing.shop_id, current_user)

    return await service.list_seller_variants(listing_id)


@router.patch(
    "/listings/{listing_id}/variants/{variant_id}",
    response_model=SellerVariantResponse,
)
async def update_seller_variant(
    listing_id: UUID,
    variant_id: UUID,
    variant_data: SellerVariantBase,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: ProductService = Depends(get_product_service),
):
    """Update seller variant price or enabled status"""
    listing = await service.get_listing(listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    await check_shop_access(db, listing.shop_id, current_user)

    update_dict = variant_data.model_dump(exclude_unset=True)
    variant = await service.update_seller_variant(listing_id, variant_id, update_dict)
    if not variant:
        raise HTTPException(status_code=404, detail="Variant not found")
    return variant


# ---- Product Media Endpoints ----


@router.get("/{product_id}/media", response_model=List[ProductMediaResponse])
async def list_product_media(
    product_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: ProductService = Depends(get_product_service),
):
    """List media for a product"""
    product = await service.get_product_raw(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    await check_shop_access(db, product.shop_id, current_user)

    return await service.list_product_media(product_id)


@router.post(
    "/{product_id}/media",
    response_model=ProductMediaResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_product_media(
    product_id: UUID,
    media_data: ProductMediaBase,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: ProductService = Depends(get_product_service),
):
    """Add media to a product"""
    product = await service.get_product_raw(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    await check_shop_access(db, product.shop_id, current_user)

    return await service.add_product_media(product_id, media_data.model_dump())


@router.delete("/media/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product_media(
    media_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: ProductService = Depends(get_product_service),
):
    """Delete product media"""
    media = await service.get_media(media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    product = await service.get_product_raw(media.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Parent product not found")
    await check_shop_access(db, product.shop_id, current_user)

    await service.delete_media(media_id)
