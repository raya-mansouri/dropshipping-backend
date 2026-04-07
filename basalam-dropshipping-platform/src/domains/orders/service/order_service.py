"""
Order Service
=============
Business logic for order lifecycle management

Handles:
- Order creation with inventory reservation
- Order state machine: pending → confirmed → paid → processing → shipped → delivered → completed
- Failure states: cancelled, disputed, refunded
- State transition validation
- Price snapshot at order time
- Order splitting by supplier
"""

import structlog
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from uuid import UUID, uuid4
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models import Order, OrderItem, OrderStatus, OrderHistory
from ..repository import OrderRepository, OrderItemRepository
from ...inventory.service.reservation_service import ReservationService
from ...inventory.repository import InventoryReservationRepository
from src.core.events.base import DomainEvent
from src.core.events.publisher import EventPublisher
from src.core.events.order import (
    OrderCreated,
    OrderCancelled,
    OrderStatusChanged,
)

logger = structlog.get_logger(__name__)


@dataclass
class OrderItemDTO:
    """Order item data transfer object"""

    id: UUID
    order_id: UUID
    supplier_shop_id: UUID
    variant_id: UUID
    quantity: int
    supplier_price: Decimal
    seller_price: Decimal
    shipping_price: Decimal
    profit: Decimal
    status: str

    @classmethod
    def from_model(cls, model: OrderItem) -> "OrderItemDTO":
        return cls(
            id=model.id,
            order_id=model.order_id,
            supplier_shop_id=model.supplier_shop_id,
            variant_id=model.variant_id,
            quantity=model.quantity,
            supplier_price=model.supplier_price,
            seller_price=model.seller_price,
            shipping_price=model.shipping_price,
            profit=model.profit or Decimal("0"),
            status=model.status,
        )


@dataclass
class OrderDTO:
    """Order data transfer object"""

    id: UUID
    shop_id: UUID
    external_order_id: Optional[str]
    customer_data: Dict[str, Any]
    total_price: Decimal
    shipping_price: Decimal
    discount: Decimal
    status: str
    notes: Optional[str]
    items: List[OrderItemDTO]
    confirmed_at: Optional[datetime]
    paid_at: Optional[datetime]
    shipped_at: Optional[datetime]
    delivered_at: Optional[datetime]
    completed_at: Optional[datetime]
    cancelled_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


VALID_TRANSITIONS = {
    OrderStatus.PENDING: [OrderStatus.CONFIRMED, OrderStatus.CANCELLED],
    OrderStatus.CONFIRMED: [OrderStatus.PAID, OrderStatus.CANCELLED],
    OrderStatus.PAID: [
        OrderStatus.PROCESSING,
        OrderStatus.REFUNDED,
        OrderStatus.DISPUTED,
    ],
    OrderStatus.PROCESSING: [OrderStatus.SHIPPED, OrderStatus.REFUNDED],
    OrderStatus.SHIPPED: [OrderStatus.DELIVERED],
    OrderStatus.DELIVERED: [OrderStatus.COMPLETED, OrderStatus.DISPUTED],
    OrderStatus.COMPLETED: [],
    OrderStatus.CANCELLED: [],
    OrderStatus.DISPUTED: [
        OrderStatus.REFUNDED,
        OrderStatus.COMPLETED,
        OrderStatus.CANCELLED,
    ],
    OrderStatus.REFUNDED: [],
}


class InvalidTransitionError(Exception):
    """Raised when an invalid state transition is attempted"""

    pass


class OrderService:
    """
    Service for managing order lifecycle.

    Handles:
    - Order creation with inventory reservation
    - State machine transitions with validation
    - Order splitting by supplier
    - Price snapshots at order time
    """

    def __init__(
        self,
        session: AsyncSession,
        event_publisher: Optional[EventPublisher] = None,
    ):
        self.session = session
        self._event_publisher = event_publisher
        self._order_repo = OrderRepository(session)
        self._order_item_repo = OrderItemRepository(session)
        self._reservation_service = ReservationService(session)
        self._reservation_repo = InventoryReservationRepository(session)

    def _can_transition(self, from_status: OrderStatus, to_status: OrderStatus) -> bool:
        """Check if a state transition is valid"""
        return to_status in VALID_TRANSITIONS.get(from_status, [])

    async def _publish_event(self, event: DomainEvent) -> None:
        """Safely publish domain event. Non-blocking - failures are logged but don't raise."""
        if self._event_publisher is None:
            return
        try:
            await self._event_publisher.publish(topic="events", event=event)
        except Exception as e:
            logger.warning("failed_to_publish_event", event_type=event.event_type, error=str(e))

    async def _record_history(
        self,
        order_id: UUID,
        from_status: Optional[OrderStatus],
        to_status: OrderStatus,
        actor_type: str = "system",
        actor_id: Optional[UUID] = None,
        order_item_id: Optional[UUID] = None,
        reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> OrderHistory:
        """Record order status change in history"""
        history = OrderHistory(
            id=uuid4(),
            order_id=order_id,
            order_item_id=order_item_id,
            from_status=from_status.value if from_status else None,
            to_status=to_status.value,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
            extra_data=metadata or {},
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(history)
        await self.session.flush()
        return history

    async def create_order(
        self,
        shop_id: UUID,
        items: List[Dict[str, Any]],
        customer_data: Optional[Dict[str, Any]] = None,
        external_order_id: Optional[str] = None,
        notes: Optional[str] = None,
        shipping_price: Decimal = Decimal("0"),
        discount: Decimal = Decimal("0"),
        reservation_minutes: int = 30,
    ) -> Order:
        """
        Create an order with inventory reservation.

        Automatically splits items by supplier and creates
        price snapshots at order time.

        Args:
            shop_id: The seller's shop UUID
            items: List of items with variant_id, quantity, seller_listing_id
            customer_data: Customer information
            external_order_id: External order ID from seller's platform
            notes: Order notes
            shipping_price: Shipping cost
            discount: Discount amount
            reservation_minutes: Minutes until inventory reservation expires

        Returns:
            Created Order with items

        Raises:
            ValueError: If inventory is insufficient or validation fails
        """
        from ...products.models import (
            SupplierVariant,
            SellerVariant,
            SellerListing,
        )
        from ...products.models import SupplierProduct

        supplier_groups: Dict[UUID, List[Dict[str, Any]]] = {}

        for item_data in items:
            variant_id = item_data["variant_id"]
            result = await self.session.execute(
                select(SupplierVariant)
                .join(
                    SupplierProduct,
                    SupplierProduct.id == SupplierVariant.supplier_product_id,
                )
                .where(SupplierVariant.id == variant_id)
            )
            variant = result.scalar_one_or_none()
            if not variant:
                raise ValueError(f"Variant {variant_id} not found")

            supplier_shop_id = variant.product.shop_id

            if seller_listing_id := item_data.get("seller_listing_id"):
                result = await self.session.execute(
                    select(SellerVariant)
                    .join(SellerListing, SellerListing.id == SellerVariant.listing_id)
                    .where(SellerVariant.listing_id == seller_listing_id)
                    .where(SellerVariant.supplier_variant_id == variant_id)
                )
                seller_variant = result.scalar_one_or_none()
                if seller_variant:
                    supplier_price = variant.cost_price
                    if seller_variant.custom_price:
                        seller_price = seller_variant.custom_price
                    else:
                        seller_price = seller_variant.price
                else:
                    seller_price = variant.cost_price
                    supplier_price = variant.cost_price
            else:
                supplier_price = variant.cost_price
                seller_price = variant.cost_price

            profit = (seller_price - supplier_price) * item_data["quantity"]

            if supplier_shop_id not in supplier_groups:
                supplier_groups[supplier_shop_id] = []

            supplier_groups[supplier_shop_id].append(
                {
                    **item_data,
                    "supplier_price": supplier_price,
                    "seller_price": seller_price,
                    "profit": profit,
                }
            )

        total_price = (
            sum(
                Decimal(str(item["seller_price"])) * item["quantity"]
                for group in supplier_groups.values()
                for item in group
            )
            + shipping_price
            - discount
        )

        order = Order(
            id=uuid4(),
            shop_id=shop_id,
            external_order_id=external_order_id,
            customer_data=customer_data or {},
            total_price=total_price,
            shipping_price=shipping_price,
            discount=discount,
            status=OrderStatus.PENDING.value,
            notes=notes,
            extra_data={},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.session.add(order)
        await self.session.flush()

        order_items = []
        for supplier_shop_id, group_items in supplier_groups.items():
            for item_data in group_items:
                order_item = OrderItem(
                    id=uuid4(),
                    order_id=order.id,
                    supplier_shop_id=supplier_shop_id,
                    variant_id=item_data["variant_id"],
                    seller_listing_id=item_data.get("seller_listing_id"),
                    quantity=item_data["quantity"],
                    supplier_price=item_data["supplier_price"],
                    seller_price=item_data["seller_price"],
                    shipping_price=Decimal("0"),
                    profit=item_data["profit"],
                    status=OrderStatus.PENDING.value,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                self.session.add(order_item)
                order_items.append(order_item)

        await self.session.flush()

        for order_item in order_items:
            try:
                await self._reservation_service.reserve_inventory(
                    variant_id=order_item.variant_id,
                    order_item_id=order_item.id,
                    quantity=order_item.quantity,
                    expires_in_minutes=reservation_minutes,
                )
            except ValueError as e:
                for item in order_items:
                    await self._reservation_service.release_inventory(
                        order_item_id=item.id,
                        reason="insufficient_inventory",
                    )
                await self.session.rollback()
                raise ValueError(f"Inventory reservation failed: {str(e)}")

        await self.session.refresh(order)

        event = OrderCreated(
            order_id=order.id,
            shop_id=shop_id,
            total_price=float(total_price),
            items_count=len(order_items),
        )
        await self._publish_event(event)

        return order

    async def transition_status(
        self,
        order_id: UUID,
        new_status: OrderStatus,
        actor_type: str = "system",
        actor_id: Optional[UUID] = None,
        reason: Optional[str] = None,
    ) -> Order:
        """
        Transition order to a new status with validation.

        Args:
            order_id: Order UUID
            new_status: Target status
            actor_type: Who initiated the change (system, seller, supplier, customer, admin)
            actor_id: UUID of the actor
            reason: Reason for the transition

        Returns:
            Updated Order

        Raises:
            ValueError: If order not found or transition invalid
        """
        order = await self._order_repo.get_by_id(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        current_status = OrderStatus(order.status)

        if not self._can_transition(current_status, new_status):
            raise InvalidTransitionError(
                f"Cannot transition from {current_status.value} to {new_status.value}"
            )

        update_data = {"status": new_status.value, "updated_at": datetime.now(timezone.utc)}

        timestamp_field = {
            OrderStatus.CONFIRMED: "confirmed_at",
            OrderStatus.PAID: "paid_at",
            OrderStatus.SHIPPED: "shipped_at",
            OrderStatus.DELIVERED: "delivered_at",
            OrderStatus.COMPLETED: "completed_at",
            OrderStatus.CANCELLED: "cancelled_at",
        }.get(new_status)

        if timestamp_field:
            update_data[timestamp_field] = datetime.now(timezone.utc)

        await self._order_repo.update(order_id, update_data)

        await self._record_history(
            order_id=order_id,
            from_status=current_status,
            to_status=new_status,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
        )

        if new_status == OrderStatus.PAID:
            order_items = await self._order_item_repo.get_by_order(order_id)
            for item in order_items:
                await self._reservation_service.consume_inventory(item.id)

        await self.session.flush()

        updated_order = await self._order_repo.get_by_id(order_id)

        status_event = OrderStatusChanged(
            order_id=order_id,
            old_status=current_status.value,
            new_status=new_status.value,
            actor=actor_type,
            metadata={"reason": reason} if reason else {},
        )
        await self._publish_event(status_event)

        return updated_order

    async def cancel_order(
        self,
        order_id: UUID,
        reason: str = "cancelled_by_seller",
        actor_type: str = "seller",
        actor_id: Optional[UUID] = None,
    ) -> Order:
        """
        Cancel an order and release inventory.

        Args:
            order_id: Order UUID
            reason: Cancellation reason
            actor_type: Who cancelled the order
            actor_id: Actor UUID

        Returns:
            Cancelled Order
        """
        order = await self._order_repo.get_by_id(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        current_status = OrderStatus(order.status)

        if current_status in [
            OrderStatus.SHIPPED,
            OrderStatus.DELIVERED,
            OrderStatus.COMPLETED,
        ]:
            raise InvalidTransitionError(
                f"Cannot cancel order in {current_status.value} status"
            )

        order_items = await self._order_item_repo.get_by_order(order_id)
        for item in order_items:
            await self._reservation_service.release_inventory(
                order_item_id=item.id,
                reason=reason,
            )

        cancelled_order = await self.transition_status(
            order_id=order_id,
            new_status=OrderStatus.CANCELLED,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
        )

        cancel_event = OrderCancelled(
            order_id=order_id,
            reason=reason,
            refunded_amount=float(order.total_price),
        )
        await self._publish_event(cancel_event)

        return cancelled_order

    async def get_order(self, order_id: UUID) -> Optional[Order]:
        """Get order by ID"""
        return await self._order_repo.get_by_id(order_id)

    async def get_orders_by_shop(self, shop_id: UUID) -> List[Order]:
        """Get all orders for a shop"""
        return await self._order_repo.get_by_shop(shop_id)

    async def get_orders_by_status(self, status: OrderStatus) -> List[Order]:
        """Get orders by status"""
        return await self._order_repo.get_by_status(status)

    async def get_order_items(self, order_id: UUID) -> List[OrderItem]:
        """Get all items for an order"""
        return await self._order_item_repo.get_by_order(order_id)

    async def split_order_by_supplier(
        self, order_id: UUID
    ) -> Dict[UUID, List[OrderItem]]:
        """
        Split order items by supplier.

        Returns:
            Dictionary mapping supplier_shop_id to list of order items
        """
        items = await self._order_item_repo.get_by_order(order_id)

        supplier_groups: Dict[UUID, List[OrderItem]] = {}
        for item in items:
            if item.supplier_shop_id not in supplier_groups:
                supplier_groups[item.supplier_shop_id] = []
            supplier_groups[item.supplier_shop_id].append(item)

        return supplier_groups

    async def get_order_history(self, order_id: UUID) -> List[OrderHistory]:
        """Get order status change history"""
        result = await self.session.execute(
            select(OrderHistory)
            .where(OrderHistory.order_id == order_id)
            .order_by(OrderHistory.created_at.desc())
        )
        return list(result.scalars().all())


class OrderItemService:
    """Service for managing order items"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self._order_item_repo = OrderItemRepository(session)

    async def get_item(self, item_id: UUID) -> Optional[OrderItem]:
        """Get order item by ID"""
        return await self._order_item_repo.get_by_id(item_id)

    async def update_item_status(
        self,
        item_id: UUID,
        status: OrderStatus,
        reject_reason: Optional[str] = None,
    ) -> OrderItem:
        """Update order item status"""
        update_data = {
            "status": status.value,
            "updated_at": datetime.now(timezone.utc),
        }

        if status == OrderStatus.CANCELLED and reject_reason:
            update_data["reject_reason"] = reject_reason
            update_data["rejected_at"] = datetime.now(timezone.utc)

        return await self._order_item_repo.update(item_id, update_data)
