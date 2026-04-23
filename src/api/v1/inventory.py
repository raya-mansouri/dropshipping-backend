"""
Inventory API Endpoints
=======================
FastAPI endpoints for inventory management
"""

from uuid import UUID
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from src.api.deps import get_db, get_current_user, check_shop_access, is_admin
from src.core.repository.unit_of_work import UnitOfWork
from src.domains.accounts.models import User
from src.domains.inventory.models import (
    InventoryReservation,
    InventorySource,
)
from src.domains.inventory.schemas import (
    VariantInventoryResponse,
    VariantInventoryListResponse,
    InventoryOverrideRequest,
    InventoryAdjustRequest,
    InventoryLogResponse,
    InventoryReservationResponse,
    ReservationStatus,
)
from src.domains.inventory.repository import (
    InventoryRepository,
    InventoryLogRepository,
)
from src.domains.products.models import SupplierVariant, SupplierProduct, ProductVariant
from src.domains.shops.models import Shop


# ============================================
# API Router
# ============================================

router = APIRouter(prefix="/inventory", tags=["inventory"])


# ---- List Variant Inventory ----


@router.get("/", response_model=VariantInventoryListResponse)
async def list_variant_inventory(
    shop_id: UUID,
    product_id: Optional[UUID] = None,
    low_stock_only: bool = Query(
        False, description="Only return variants with low stock"
    ),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List variant inventory for a shop.

    Returns variant details with stock counts.
    Optionally filter by product_id or low-stock variants only.
    """
    await check_shop_access(db, shop_id, current_user)

    # Build base query: SupplierVariant joined to SupplierProduct (for shop filter)
    # and ProductVariant (for sku / attributes)
    base_query = (
        select(SupplierVariant)
        .join(SupplierProduct, SupplierVariant.supplier_product_id == SupplierProduct.id)
        .where(SupplierProduct.shop_id == shop_id)
    )

    if product_id:
        base_query = base_query.where(SupplierProduct.id == product_id)

    if low_stock_only:
        base_query = base_query.where(
            SupplierVariant.inventory - SupplierVariant.reserved_inventory <= 5
        )

    # Count total matching rows
    count_query = select(func.count()).select_from(base_query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Fetch page of results
    data_query = (
        base_query.order_by(SupplierVariant.updated_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(data_query)
    supplier_variants = result.scalars().all()

    # Batch-load ProductVariant data for sku/attributes
    pv_ids = [sv.variant_id for sv in supplier_variants]
    pv_map: dict = {}
    if pv_ids:
        pv_result = await db.execute(
            select(ProductVariant).where(ProductVariant.id.in_(pv_ids))
        )
        for pv in pv_result.scalars().all():
            pv_map[pv.id] = pv

    items = []
    for sv in supplier_variants:
        pv = pv_map.get(sv.variant_id)
        items.append(
            VariantInventoryResponse(
                id=sv.id,
                variant_id=sv.variant_id,
                sku=pv.sku if pv else None,
                attributes=pv.attributes if pv else {},
                cost_price=sv.cost_price,
                inventory=sv.inventory,
                reserved_inventory=sv.reserved_inventory,
                available_inventory=sv.available_inventory,
                status=sv.status,
                updated_at=sv.updated_at,
            )
        )

    return VariantInventoryListResponse(items=items, total=total)


# ---- Manual Inventory Override ----


@router.patch("/{variant_id}", response_model=VariantInventoryResponse)
async def override_inventory(
    variant_id: UUID,
    body: InventoryOverrideRequest,
    shop_id: UUID = Query(..., description="Shop that owns this variant"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Manual inventory override.

    Sets inventory to an absolute value. Only allowed for supplier shops.
    Creates an InventoryLog entry for audit.
    """
    await check_shop_access(db, shop_id, current_user)

    # Verify shop is a supplier shop
    shop_result = await db.execute(select(Shop).where(Shop.id == shop_id))
    shop = shop_result.scalar_one_or_none()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    if shop.shop_role != "supplier":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inventory override is only allowed for supplier shops",
        )

    async with UnitOfWork(db) as uow:
        session = uow.session

        # Load variant and verify it belongs to the shop
        inv_repo = InventoryRepository(session)
        supplier_variant = await inv_repo.get_by_variant_id(variant_id)
        if not supplier_variant:
            raise HTTPException(status_code=404, detail="Variant not found")

        # Ownership check: variant's product must belong to this shop
        product_result = await session.execute(
            select(SupplierProduct.id).where(
                SupplierProduct.id == supplier_variant.supplier_product_id,
                SupplierProduct.shop_id == shop_id,
            )
        )
        if not product_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Variant does not belong to this shop",
            )

        old_inventory = supplier_variant.inventory
        new_inventory = body.quantity

        supplier_variant.inventory = new_inventory
        await uow.flush()

        # Load ProductVariant for response enrichment
        pv_result = await session.execute(
            select(ProductVariant).where(
                ProductVariant.id == supplier_variant.variant_id
            )
        )
        pv = pv_result.scalar_one_or_none()

        # Create audit log
        log_repo = InventoryLogRepository(session)
        await log_repo.create(
            {
                "variant_id": supplier_variant.id,
                "old_inventory": old_inventory,
                "new_inventory": new_inventory,
                "change": new_inventory - old_inventory,
                "source": InventorySource.MANUAL.value,
                "reference_type": "manual",
                "reason": body.reason,
            }
        )

        await uow.flush()
        await uow.refresh(supplier_variant)
        await uow.commit()

    return VariantInventoryResponse(
        id=supplier_variant.id,
        variant_id=supplier_variant.variant_id,
        sku=pv.sku if pv else None,
        attributes=pv.attributes if pv else {},
        cost_price=supplier_variant.cost_price,
        inventory=supplier_variant.inventory,
        reserved_inventory=supplier_variant.reserved_inventory,
        available_inventory=supplier_variant.available_inventory,
        status=supplier_variant.status,
        updated_at=supplier_variant.updated_at,
    )


# ---- List Active Reservations ----


@router.get("/reservations", response_model=List[InventoryReservationResponse])
async def list_reservations(
    shop_id: Optional[UUID] = None,
    status_filter: Optional[ReservationStatus] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List active inventory reservations.

    Optionally filter by shop or reservation status.
    """
    if shop_id:
        await check_shop_access(db, shop_id, current_user)

    query = select(InventoryReservation)

    if shop_id:
        # Filter reservations whose variant belongs to a product in this shop
        query = (
            query.join(
                SupplierVariant,
                InventoryReservation.variant_id == SupplierVariant.id,
            )
            .join(
                SupplierProduct,
                SupplierVariant.supplier_product_id == SupplierProduct.id,
            )
            .where(SupplierProduct.shop_id == shop_id)
        )
    elif not is_admin(current_user):
        # Scope to user's shops
        from src.domains.accounts.models import Account

        user_shops = (
            select(Shop.id)
            .join(Account, Shop.account_id == Account.id)
            .where(Account.owner_user_id == current_user.id)
        )
        query = (
            query.join(
                SupplierVariant, InventoryReservation.variant_id == SupplierVariant.id
            )
            .join(
                SupplierProduct,
                SupplierVariant.supplier_product_id == SupplierProduct.id,
            )
            .where(SupplierProduct.shop_id.in_(user_shops))
        )

    if status_filter:
        query = query.where(InventoryReservation.status == status_filter.value)

    query = (
        query.order_by(InventoryReservation.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    result = await db.execute(query)
    return result.scalars().all()


# ---- Adjust Inventory ----


@router.post("/{variant_id}/adjust", response_model=InventoryLogResponse)
async def adjust_inventory(
    variant_id: UUID,
    body: InventoryAdjustRequest,
    shop_id: UUID = Query(..., description="Shop that owns this variant"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Adjust inventory by a relative amount.

    Creates an InventoryLog entry for audit.
    Positive quantity_change adds stock, negative subtracts.
    """
    await check_shop_access(db, shop_id, current_user)

    async with UnitOfWork(db) as uow:
        session = uow.session

        inv_repo = InventoryRepository(session)
        supplier_variant = await inv_repo.get_by_variant_id(variant_id)
        if not supplier_variant:
            raise HTTPException(status_code=404, detail="Variant not found")

        # Ownership check
        product_result = await session.execute(
            select(SupplierProduct.id).where(
                SupplierProduct.id == supplier_variant.supplier_product_id,
                SupplierProduct.shop_id == shop_id,
            )
        )
        if not product_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Variant does not belong to this shop",
            )

        old_inventory = supplier_variant.inventory
        new_inventory = old_inventory + body.quantity_change

        if new_inventory < 0:
            raise HTTPException(
                status_code=400,
                detail=f"Adjustment would result in negative inventory ({new_inventory})",
            )

        supplier_variant.inventory = new_inventory
        await uow.flush()

        # Create audit log
        log_repo = InventoryLogRepository(session)
        log_entry = await log_repo.create(
            {
                "variant_id": supplier_variant.id,
                "old_inventory": old_inventory,
                "new_inventory": new_inventory,
                "change": body.quantity_change,
                "source": InventorySource.MANUAL.value,
                "reference_type": "manual",
                "reason": body.reason,
            }
        )

        await uow.flush()
        await uow.commit()

    return log_entry
