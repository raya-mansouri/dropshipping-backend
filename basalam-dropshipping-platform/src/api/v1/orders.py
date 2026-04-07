"""
Orders API Endpoints
====================
FastAPI endpoints for order management
"""

from uuid import UUID
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone

from src.api.deps import get_db, get_current_user
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
from src.domains.products.models import SupplierVariant, SellerVariant


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
):
    """
    Create a new order

    Validates inventory availability and creates order with items
    """
    total_price = 0
    order_items = []

    for item_data in order_data.items:
        result = await db.execute(
            select(SupplierVariant).where(
                SupplierVariant.variant_id == item_data.variant_id
            )
        )
        supplier_variant = result.scalar_one_or_none()
        if not supplier_variant:
            raise HTTPException(
                status_code=404, detail=f"Variant {item_data.variant_id} not found"
            )

        if supplier_variant.available_inventory < item_data.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient inventory for variant {item_data.variant_id}",
            )

        seller_result = None
        if item_data.seller_listing_id:
            seller_result = await db.execute(
                select(SellerVariant).where(
                    SellerVariant.listing_id == item_data.seller_listing_id,
                    SellerVariant.supplier_variant_id == supplier_variant.id,
                )
            )
            seller_variant = seller_result.scalar_one_or_none()
            seller_price = (
                seller_variant.price if seller_variant else supplier_variant.cost_price
            )
        else:
            seller_price = supplier_variant.cost_price

        profit = seller_price - supplier_variant.cost_price

        order_items.append(
            {
                "variant_id": item_data.variant_id,
                "quantity": item_data.quantity,
                "seller_listing_id": item_data.seller_listing_id,
                "supplier_price": supplier_variant.cost_price,
                "seller_price": seller_price,
                "profit": profit * item_data.quantity,
            }
        )

        total_price += seller_price * item_data.quantity

    order = Order(
        shop_id=shop_id,
        external_order_id=external_order_id,
        customer_data=order_data.customer_data,
        total_price=total_price,
        notes=order_data.notes,
        status=ModelOrderStatus.PENDING.value,
    )
    db.add(order)
    await db.flush()

    for item_dict in order_items:
        order_item = OrderItem(order_id=order.id, supplier_shop_id=shop_id, **item_dict)
        db.add(order_item)

    history = OrderHistory(
        order_id=order.id,
        to_status=ModelOrderStatus.PENDING.value,
        actor_type="system",
        reason="Order created",
    )
    db.add(history)

    await db.refresh(order)
    return order


@router.get("/", response_model=List[OrderResponse])
async def list_orders(
    db: AsyncSession = Depends(get_db),
    shop_id: Optional[UUID] = None,
    status: Optional[SchemaOrderStatus] = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
):
    """List orders with filters"""
    query = select(Order)

    if shop_id:
        query = query.where(Order.shop_id == shop_id)
    if status:
        query = query.where(Order.status == status.value)

    query = query.limit(limit).offset(offset).order_by(Order.created_at.desc())

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(order_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get order by ID"""
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.patch("/{order_id}", response_model=OrderResponse)
async def update_order(
    order_id: UUID, order_data: OrderUpdate, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update order status or notes"""
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    update_dict = order_data.model_dump(exclude_unset=True)

    if "status" in update_dict:
        new_status = update_dict["status"]
        old_status = order.status

        setattr(order, f"{new_status.value}_at", datetime.now(timezone.utc))

        history = OrderHistory(
            order_id=order.id,
            from_status=old_status,
            to_status=new_status.value,
            actor_type="system",
            reason="Status updated",
        )
        db.add(history)

    for field, value in update_dict.items():
        setattr(order, field, value)

    await db.flush()
    await db.refresh(order)
    return order


# ---- Cancel Order ----


@router.post("/{order_id}/cancel", response_model=OrderResponse)
async def cancel_order(
    order_id: UUID, reason: Optional[str] = None, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Cancel an order

    Only orders in certain statuses can be cancelled
    """
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    cancellable_statuses = [
        ModelOrderStatus.PENDING.value,
        ModelOrderStatus.CONFIRMED.value,
    ]

    if order.status not in cancellable_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Order in '{order.status}' status cannot be cancelled",
        )

    old_status = order.status
    order.status = ModelOrderStatus.CANCELLED.value
    order.cancelled_at = datetime.now(timezone.utc)

    history = OrderHistory(
        order_id=order.id,
        from_status=old_status,
        to_status=ModelOrderStatus.CANCELLED.value,
        actor_type="user",
        reason=reason or "Order cancelled",
    )
    db.add(history)

    await db.flush()
    await db.refresh(order)
    return order


# ---- Order Items ----


@router.get("/{order_id}/items", response_model=List[OrderItemResponse])
async def list_order_items(order_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """List items for an order"""
    order_result = await db.execute(select(Order).where(Order.id == order_id))
    if not order_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Order not found")

    result = await db.execute(select(OrderItem).where(OrderItem.order_id == order_id))
    return result.scalars().all()


@router.get("/items/{item_id}", response_model=OrderItemResponse)
async def get_order_item(item_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get order item by ID"""
    result = await db.execute(select(OrderItem).where(OrderItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Order item not found")
    return item


# ---- Order History ----


@router.get("/{order_id}/history", response_model=List[OrderHistoryResponse])
async def list_order_history(order_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get order status history"""
    order_result = await db.execute(select(Order).where(Order.id == order_id))
    if not order_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Order not found")

    result = await db.execute(
        select(OrderHistory)
        .where(OrderHistory.order_id == order_id)
        .order_by(OrderHistory.created_at)
    )
    return result.scalars().all()


# ---- Shipment Endpoints ----


@router.get("/{order_id}/shipments", response_model=List[ShipmentResponse])
async def list_shipments(order_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """List shipments for an order"""
    order_result = await db.execute(select(Order).where(Order.id == order_id))
    if not order_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Order not found")

    result = await db.execute(select(Shipment).where(Shipment.order_id == order_id))
    return result.scalars().all()


@router.get("/shipments/{shipment_id}", response_model=ShipmentResponse)
async def get_shipment(shipment_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get shipment by ID"""
    result = await db.execute(select(Shipment).where(Shipment.id == shipment_id))
    shipment = result.scalar_one_or_none()
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return shipment


@router.post("/shipments/{shipment_id}/confirm-delivery")
async def confirm_delivery(
    shipment_id: UUID,
    confirm_data: DeliveryConfirmRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Confirm delivery of a shipment"""
    result = await db.execute(select(Shipment).where(Shipment.id == shipment_id))
    shipment = result.scalar_one_or_none()
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")

    shipment.delivery_confirmed_at = datetime.now(timezone.utc)
    shipment.delivery_confirmed_by = confirm_data.confirmed_by
    shipment.status = ShipmentStatus.DELIVERED.value

    await db.flush()
    return {"status": "delivery confirmed"}


# ---- Order Status Transitions ----


@router.post("/{order_id}/confirm", response_model=OrderResponse)
async def confirm_order(order_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Confirm an order"""
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status != ModelOrderStatus.PENDING.value:
        raise HTTPException(
            status_code=400, detail="Only pending orders can be confirmed"
        )

    old_status = order.status
    order.status = ModelOrderStatus.CONFIRMED.value
    order.confirmed_at = datetime.now(timezone.utc)

    history = OrderHistory(
        order_id=order.id,
        from_status=old_status,
        to_status=ModelOrderStatus.CONFIRMED.value,
        actor_type="user",
        reason="Order confirmed",
    )
    db.add(history)

    await db.flush()
    await db.refresh(order)
    return order


@router.post("/{order_id}/mark-paid", response_model=OrderResponse)
async def mark_order_paid(order_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Mark order as paid"""
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status != ModelOrderStatus.CONFIRMED.value:
        raise HTTPException(
            status_code=400, detail="Only confirmed orders can be marked as paid"
        )

    old_status = order.status
    order.status = ModelOrderStatus.PAID.value
    order.paid_at = datetime.now(timezone.utc)

    history = OrderHistory(
        order_id=order.id,
        from_status=old_status,
        to_status=ModelOrderStatus.PAID.value,
        actor_type="system",
        reason="Payment received",
    )
    db.add(history)

    await db.flush()
    await db.refresh(order)
    return order


@router.post("/{order_id}/mark-shipped", response_model=OrderResponse)
async def mark_order_shipped(
    order_id: UUID,
    tracking_code: Optional[str] = None,
    carrier: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark order as shipped"""
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status != ModelOrderStatus.PAID.value:
        raise HTTPException(
            status_code=400, detail="Only paid orders can be marked as shipped"
        )

    old_status = order.status
    order.status = ModelOrderStatus.SHIPPED.value
    order.shipped_at = datetime.now(timezone.utc)

    if tracking_code or carrier:
        for item in order.items:
            shipment = Shipment(
                order_id=order.id,
                order_item_id=item.id,
                tracking_code=tracking_code,
                carrier=carrier,
                status=ShipmentStatus.SHIPPED.value,
                shipped_at=datetime.now(timezone.utc),
            )
            db.add(shipment)

    history = OrderHistory(
        order_id=order.id,
        from_status=old_status,
        to_status=ModelOrderStatus.SHIPPED.value,
        actor_type="system",
        reason="Order shipped",
    )
    db.add(history)

    await db.flush()
    await db.refresh(order)
    return order


@router.post("/{order_id}/mark-delivered", response_model=OrderResponse)
async def mark_order_delivered(order_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Mark order as delivered"""
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status != ModelOrderStatus.SHIPPED.value:
        raise HTTPException(
            status_code=400, detail="Only shipped orders can be marked as delivered"
        )

    old_status = order.status
    order.status = ModelOrderStatus.DELIVERED.value
    order.delivered_at = datetime.now(timezone.utc)

    history = OrderHistory(
        order_id=order.id,
        from_status=old_status,
        to_status=ModelOrderStatus.DELIVERED.value,
        actor_type="customer",
        reason="Order delivered",
    )
    db.add(history)

    await db.flush()
    await db.refresh(order)
    return order


@router.post("/{order_id}/complete", response_model=OrderResponse)
async def complete_order(order_id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Complete an order (final status)"""
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status != ModelOrderStatus.DELIVERED.value:
        raise HTTPException(
            status_code=400, detail="Only delivered orders can be completed"
        )

    old_status = order.status
    order.status = ModelOrderStatus.COMPLETED.value
    order.completed_at = datetime.now(timezone.utc)

    history = OrderHistory(
        order_id=order.id,
        from_status=old_status,
        to_status=ModelOrderStatus.COMPLETED.value,
        actor_type="system",
        reason="Order completed",
    )
    db.add(history)

    await db.flush()
    await db.refresh(order)
    return order
