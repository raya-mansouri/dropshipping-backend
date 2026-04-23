"""
Orders API Endpoints
====================
FastAPI endpoints for order management

Delegates business logic to OrderService and repositories.
"""

import structlog
from uuid import UUID
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone

from src.api.deps import (
    get_db,
    get_current_user,
    check_shop_access,
    is_admin,
    get_order_service,
)
from src.domains.accounts.models import User
from src.domains.orders.models import (
    Order,
    OrderItem,
    OrderHistory,
    Shipment,
    OrderStatus as ModelOrderStatus,
)
from src.domains.orders.schemas import (
    OrderResponse,
    OrderCreate,
    OrderUpdate,
    OrderItemResponse,
    ShipmentResponse,
    ShipmentStatus,
    DeliveryConfirmRequest,
    OrderHistoryResponse,
    OrderStatus as SchemaOrderStatus,
)
from src.domains.orders.service.order_service import (
    OrderService,
    InvalidTransitionError,
)
from src.domains.orders.repository import ShipmentRepository, OrderItemRepository
from src.domains.shops.models import Shop
from src.domains.accounts.models import Account

logger = structlog.get_logger(__name__)


# ============================================
# API Router
# ============================================

router = APIRouter(prefix="/orders", tags=["orders"])


# ---- Order Endpoints ----


@router.post("/", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    order_data: OrderCreate,
    shop_id: UUID,
    external_order_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    order_service: OrderService = Depends(get_order_service),
):
    """
    Create a new order

    Validates inventory availability and creates order with items
    """
    await check_shop_access(db, shop_id, current_user)

    items_payload = [
        {
            "variant_id": str(item.variant_id),
            "quantity": item.quantity,
            "seller_listing_id": str(item.seller_listing_id) if item.seller_listing_id else None,
        }
        for item in order_data.items
    ]

    try:
        order = await order_service.create_order(
            shop_id=shop_id,
            items=items_payload,
            customer_data=order_data.customer_data,
            external_order_id=external_order_id,
            notes=order_data.notes,
        )
    except ValueError as e:
        detail = str(e)
        if "not found" in detail.lower():
            raise HTTPException(status_code=404, detail=detail)
        raise HTTPException(status_code=400, detail=detail)

    return order


@router.get("/", response_model=List[OrderResponse])
async def list_orders(
    db: AsyncSession = Depends(get_db),
    shop_id: Optional[UUID] = None,
    status: Optional[SchemaOrderStatus] = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    order_service: OrderService = Depends(get_order_service),
):
    """List orders with filters. Scoped to user's shops unless admin."""
    if shop_id:
        await check_shop_access(db, shop_id, current_user)

    if shop_id:
        orders = await order_service.get_orders_by_shop(shop_id)
        if status:
            orders = [o for o in orders if o.status == status.value]
        orders = orders[offset : offset + limit]
    elif status:
        orders = await order_service.get_orders_by_status(ModelOrderStatus(status.value))
        orders = orders[offset : offset + limit]
    elif not is_admin(current_user):
        # Scope to orders belonging to user's shops
        user_shops_result = await db.execute(
            select(Shop.id)
            .join(Account, Shop.account_id == Account.id)
            .where(Account.owner_user_id == current_user.id)
        )
        user_shop_ids = [row[0] for row in user_shops_result.all()]
        all_orders = []
        for sid in user_shop_ids:
            shop_orders = await order_service.get_orders_by_shop(sid)
            all_orders.extend(shop_orders)
        all_orders.sort(key=lambda o: o.created_at, reverse=True)
        orders = all_orders[offset : offset + limit]
    else:
        # Admin with no filters: paginate across all shops via service
        # Fall back to a single-shop approach using the first available shop
        # or an empty list if no shops exist. This matches the original
        # behaviour where an unfiltered admin query returned all orders.
        result = await db.execute(
            select(Order)
            .order_by(Order.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        orders = list(result.scalars().all())

    return orders


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    order_service: OrderService = Depends(get_order_service),
):
    """Get order by ID"""
    order = await order_service.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    await check_shop_access(db, order.shop_id, current_user)
    return order


@router.patch("/{order_id}", response_model=OrderResponse)
async def update_order(
    order_id: UUID,
    order_data: OrderUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    order_service: OrderService = Depends(get_order_service),
):
    """Update order status or notes"""
    order = await order_service.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    await check_shop_access(db, order.shop_id, current_user)

    update_dict = order_data.model_dump(exclude_unset=True)

    if "status" in update_dict:
        new_status = update_dict["status"]
        try:
            order = await order_service.transition_status(
                order_id=order_id,
                new_status=ModelOrderStatus(new_status.value),
                actor_type="system",
                reason="Status updated",
            )
        except InvalidTransitionError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    if "notes" in update_dict:
        from src.domains.orders.repository import OrderRepository

        repo = OrderRepository(db)
        order = await repo.update(order_id, {"notes": update_dict["notes"]})

    return order


# ---- Cancel Order ----


@router.post("/{order_id}/cancel", response_model=OrderResponse)
async def cancel_order(
    order_id: UUID,
    reason: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    order_service: OrderService = Depends(get_order_service),
):
    """
    Cancel an order

    Only orders in certain statuses can be cancelled
    """
    order = await order_service.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    await check_shop_access(db, order.shop_id, current_user)

    try:
        order = await order_service.cancel_order(
            order_id=order_id,
            reason=reason or "Order cancelled",
            actor_type="user",
            actor_id=current_user.id,
        )
    except InvalidTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return order


# ---- Order Items ----


@router.get("/{order_id}/items", response_model=List[OrderItemResponse])
async def list_order_items(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    order_service: OrderService = Depends(get_order_service),
):
    """List items for an order"""
    order = await order_service.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    await check_shop_access(db, order.shop_id, current_user)

    return await order_service.get_order_items(order_id)


@router.get("/items/{item_id}", response_model=OrderItemResponse)
async def get_order_item(
    item_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    order_service: OrderService = Depends(get_order_service),
):
    """Get order item by ID"""
    item_repo = OrderItemRepository(db)
    item = await item_repo.get_by_id(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Order item not found")

    order = await order_service.get_order(item.order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Parent order not found")
    await check_shop_access(db, order.shop_id, current_user)
    return item


# ---- Order History ----


@router.get("/{order_id}/history", response_model=List[OrderHistoryResponse])
async def list_order_history(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    order_service: OrderService = Depends(get_order_service),
):
    """Get order status history"""
    order = await order_service.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    await check_shop_access(db, order.shop_id, current_user)

    return await order_service.get_order_history(order_id)


# ---- Shipment Endpoints ----


@router.get("/{order_id}/shipments", response_model=List[ShipmentResponse])
async def list_shipments(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    order_service: OrderService = Depends(get_order_service),
):
    """List shipments for an order"""
    order = await order_service.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    await check_shop_access(db, order.shop_id, current_user)

    shipment_repo = ShipmentRepository(db)
    return await shipment_repo.get_by_order(order_id)


@router.get("/shipments/{shipment_id}", response_model=ShipmentResponse)
async def get_shipment(
    shipment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    order_service: OrderService = Depends(get_order_service),
):
    """Get shipment by ID"""
    shipment_repo = ShipmentRepository(db)
    shipment = await shipment_repo.get_by_id(shipment_id)
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")

    order = await order_service.get_order(shipment.order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Parent order not found")
    await check_shop_access(db, order.shop_id, current_user)
    return shipment


@router.post("/shipments/{shipment_id}/confirm-delivery")
async def confirm_delivery(
    shipment_id: UUID,
    confirm_data: DeliveryConfirmRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    order_service: OrderService = Depends(get_order_service),
):
    """Confirm delivery of a shipment"""
    shipment_repo = ShipmentRepository(db)
    shipment = await shipment_repo.get_by_id(shipment_id)
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")

    order = await order_service.get_order(shipment.order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Parent order not found")
    await check_shop_access(db, order.shop_id, current_user)

    await shipment_repo.update(
        shipment_id,
        {
            "delivery_confirmed_at": datetime.now(timezone.utc),
            "delivery_confirmed_by": confirm_data.confirmed_by,
            "status": ShipmentStatus.DELIVERED.value,
        },
    )

    return {"status": "delivery confirmed"}


# ---- Order Status Transitions ----


@router.post("/{order_id}/confirm", response_model=OrderResponse)
async def confirm_order(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    order_service: OrderService = Depends(get_order_service),
):
    """Confirm an order"""
    order = await order_service.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    await check_shop_access(db, order.shop_id, current_user)

    try:
        order = await order_service.transition_status(
            order_id=order_id,
            new_status=ModelOrderStatus.CONFIRMED,
            actor_type="user",
            reason="Order confirmed",
        )
    except InvalidTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return order


@router.post("/{order_id}/mark-paid", response_model=OrderResponse)
async def mark_order_paid(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    order_service: OrderService = Depends(get_order_service),
):
    """Mark order as paid"""
    order = await order_service.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    await check_shop_access(db, order.shop_id, current_user)

    try:
        order = await order_service.transition_status(
            order_id=order_id,
            new_status=ModelOrderStatus.PAID,
            actor_type="system",
            reason="Payment received",
        )
    except InvalidTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return order


@router.post("/{order_id}/mark-shipped", response_model=OrderResponse)
async def mark_order_shipped(
    order_id: UUID,
    tracking_code: Optional[str] = None,
    carrier: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    order_service: OrderService = Depends(get_order_service),
):
    """Mark order as shipped"""
    order = await order_service.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    await check_shop_access(db, order.shop_id, current_user)

    try:
        order = await order_service.transition_status(
            order_id=order_id,
            new_status=ModelOrderStatus.SHIPPED,
            actor_type="system",
            reason="Order shipped",
        )
    except InvalidTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if tracking_code or carrier:
        items = await order_service.get_order_items(order_id)
        shipment_repo = ShipmentRepository(db)
        for item in items:
            await shipment_repo.create(
                {
                    "order_id": order_id,
                    "order_item_id": item.id,
                    "tracking_code": tracking_code,
                    "carrier": carrier,
                    "status": ShipmentStatus.SHIPPED.value,
                    "shipped_at": datetime.now(timezone.utc),
                }
            )

    return order


@router.post("/{order_id}/mark-delivered", response_model=OrderResponse)
async def mark_order_delivered(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    order_service: OrderService = Depends(get_order_service),
):
    """Mark order as delivered"""
    order = await order_service.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    await check_shop_access(db, order.shop_id, current_user)

    try:
        order = await order_service.transition_status(
            order_id=order_id,
            new_status=ModelOrderStatus.DELIVERED,
            actor_type="customer",
            reason="Order delivered",
        )
    except InvalidTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return order


@router.post("/{order_id}/complete", response_model=OrderResponse)
async def complete_order(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    order_service: OrderService = Depends(get_order_service),
):
    """Complete an order (final status)"""
    order = await order_service.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    await check_shop_access(db, order.shop_id, current_user)

    try:
        order = await order_service.transition_status(
            order_id=order_id,
            new_status=ModelOrderStatus.COMPLETED,
            actor_type="system",
            reason="Order completed",
        )
    except InvalidTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return order
