"""
Shipping API Endpoints
======================
FastAPI endpoints for shipment tracking and shipping methods
"""

from uuid import UUID, uuid4
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone

from src.api.deps import get_db, get_current_user, check_shop_access, is_admin
from src.domains.accounts.models import User, Account
from src.domains.orders.models import Order, OrderItem, Shipment
from src.domains.orders.schemas import (
    ShipmentResponse,
    ShipmentStatus,
)
from src.domains.shipping.schemas import (
    ShipmentTrackingUpdate,
    ShippingMethodResponse,
)
from src.domains.shipping.service.shipping_service import ShippingService
from src.domains.shipping.repository.shipping_method_repository import ShippingMethodRepository
from src.domains.shops.models import Shop
from src.domains.shops.repository.shop import ShopRepository


# ============================================
# API Router
# ============================================

router = APIRouter(prefix="/shipping", tags=["shipping"])


# ---- Shipment Endpoints ----


@router.get("/shipments", response_model=List[ShipmentResponse])
async def list_shipments(
    order_id: Optional[UUID] = None,
    status: Optional[ShipmentStatus] = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List shipments with optional filters. Scoped to user's shops unless admin."""
    query = select(Shipment)

    if order_id:
        query = query.where(Shipment.order_id == order_id)
    elif not is_admin(current_user):
        # Scope to shipments belonging to orders from user's shops
        user_shops = (
            select(Shop.id)
            .join(Account, Shop.account_id == Account.id)
            .where(Account.owner_user_id == current_user.id)
        )
        query = query.where(
            Shipment.order_id.in_(
                select(Order.id).where(Order.shop_id.in_(user_shops))
            )
        )

    if status:
        query = query.where(Shipment.status == status.value)

    query = query.limit(limit).offset(offset).order_by(Shipment.created_at.desc())

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/shipments/{shipment_id}", response_model=ShipmentResponse)
async def get_shipment(
    shipment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get shipment by ID"""
    result = await db.execute(select(Shipment).where(Shipment.id == shipment_id))
    shipment = result.scalar_one_or_none()
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")
    # Verify ownership via the order's shop
    order_result = await db.execute(select(Order).where(Order.id == shipment.order_id))
    order = order_result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Parent order not found")
    await check_shop_access(db, order.shop_id, current_user)
    return shipment


@router.patch("/shipments/{shipment_id}/tracking", response_model=ShipmentResponse)
async def update_tracking(
    shipment_id: UUID,
    tracking_data: ShipmentTrackingUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Update tracking information for a shipment.

    Only accessible by supplier shop owners. The shipment must belong to
    an order item sourced from the supplier's shop.
    """
    result = await db.execute(select(Shipment).where(Shipment.id == shipment_id))
    shipment = result.scalar_one_or_none()
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")

    # Load the order item to get the supplier shop id
    item_result = await db.execute(
        select(OrderItem).where(OrderItem.id == shipment.order_item_id)
    )
    order_item = item_result.scalar_one_or_none()
    if not order_item:
        raise HTTPException(status_code=404, detail="Order item not found")

    # Verify the current user owns the SUPPLIER shop for this order item
    shop_repo = ShopRepository(db)
    supplier_shop = await shop_repo.get_by_id_and_owner(
        order_item.supplier_shop_id, current_user.id
    )
    if not supplier_shop and not is_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only supplier shop owners can update tracking info",
        )
    if supplier_shop and supplier_shop.shop_role != "supplier" and not is_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only supplier shop owners can update tracking info",
        )

    shipping_service = ShippingService(db)
    updated_shipment = await shipping_service.update_tracking(
        shipment_id=shipment_id,
        tracking_code=tracking_data.tracking_code,
        carrier=tracking_data.carrier,
        status=tracking_data.status,
    )
    if not updated_shipment:
        raise HTTPException(status_code=404, detail="Shipment update failed")
    return updated_shipment


@router.post("/shipments/{shipment_id}/confirm-delivery")
async def confirm_delivery(
    shipment_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Confirm delivery of a shipment.

    Triggers payout release for the supplier via a DeliveryConfirmed domain event.
    """
    result = await db.execute(select(Shipment).where(Shipment.id == shipment_id))
    shipment = result.scalar_one_or_none()
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")

    # Verify ownership via the order's shop
    order_result = await db.execute(select(Order).where(Order.id == shipment.order_id))
    order = order_result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Parent order not found")
    await check_shop_access(db, order.shop_id, current_user)

    if shipment.status not in ("shipped", "in_transit"):
        raise HTTPException(
            status_code=400,
            detail=f"Shipment in '{shipment.status}' status cannot be confirmed as delivered",
        )

    shipping_service = ShippingService(db)
    updated = await shipping_service.confirm_delivery(
        shipment_id=shipment_id,
        confirmed_by="customer",
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Shipment delivery confirmation failed")

    # Publish DeliveryConfirmed event to trigger payout release
    import structlog

    logger = structlog.get_logger(__name__)
    try:
        from src.core.events.base import DomainEvent

        event = DomainEvent(
            event_id=uuid4(),
            event_type="DeliveryConfirmed",
            occurred_at=datetime.now(timezone.utc),
            metadata={
                "shipment_id": str(shipment.id),
                "order_id": str(shipment.order_id),
                "order_item_id": str(shipment.order_item_id),
                "confirmed_by": "customer",
            },
        )

        publisher = request.app.state.event_publisher
        await publisher.publish("order.shipped", event)
    except Exception:
        # Log but don't fail the request if event publishing fails
        logger.error(
            "failed_to_publish_delivery_confirmed_event",
            shipment_id=str(shipment_id),
            exc_info=True,
        )

    return {"status": "delivery confirmed", "shipment_id": str(shipment_id)}


# ---- Shipping Method Endpoints ----


@router.get("/methods", response_model=List[ShippingMethodResponse])
async def list_shipping_methods(
    platform_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List available shipping methods, optionally filtered by platform."""
    method_repo = ShippingMethodRepository(db)

    if platform_id:
        methods = await method_repo.get_by_platform(platform_id)
    else:
        methods = await method_repo.get_all_active()

    return methods
