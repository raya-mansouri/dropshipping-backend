from datetime import datetime
from typing import Dict, Any
from uuid import UUID, uuid4

from .base import DomainEvent


class OrderCreated(DomainEvent):
    def __init__(
        self,
        order_id: UUID,
        shop_id: UUID,
        total_price: float,
        items_count: int,
        occurred_at: datetime = None,
        metadata: Dict[str, Any] = None,
    ):
        super().__init__(
            event_id=uuid4(),
            event_type="OrderCreated",
            occurred_at=occurred_at or datetime.utcnow(),
            metadata=metadata,
        )
        self.order_id = order_id
        self.shop_id = shop_id
        self.total_price = total_price
        self.items_count = items_count


class OrderPaid(DomainEvent):
    def __init__(
        self,
        order_id: UUID,
        payment_id: UUID,
        amount: float,
        occurred_at: datetime = None,
        metadata: Dict[str, Any] = None,
    ):
        super().__init__(
            event_id=uuid4(),
            event_type="OrderPaid",
            occurred_at=occurred_at or datetime.utcnow(),
            metadata=metadata,
        )
        self.order_id = order_id
        self.payment_id = payment_id
        self.amount = amount


class OrderCancelled(DomainEvent):
    def __init__(
        self,
        order_id: UUID,
        reason: str,
        refunded_amount: float,
        occurred_at: datetime = None,
        metadata: Dict[str, Any] = None,
    ):
        super().__init__(
            event_id=uuid4(),
            event_type="OrderCancelled",
            occurred_at=occurred_at or datetime.utcnow(),
            metadata=metadata,
        )
        self.order_id = order_id
        self.reason = reason
        self.refunded_amount = refunded_amount


class OrderStatusChanged(DomainEvent):
    def __init__(
        self,
        order_id: UUID,
        old_status: str,
        new_status: str,
        actor: str,
        occurred_at: datetime = None,
        metadata: Dict[str, Any] = None,
    ):
        super().__init__(
            event_id=uuid4(),
            event_type="OrderStatusChanged",
            occurred_at=occurred_at or datetime.utcnow(),
            metadata=metadata,
        )
        self.order_id = order_id
        self.old_status = old_status
        self.new_status = new_status
        self.actor = actor


class OrderShipped(DomainEvent):
    def __init__(
        self,
        order_id: UUID,
        shipment_id: UUID,
        tracking_code: str,
        carrier: str,
        occurred_at: datetime = None,
        metadata: Dict[str, Any] = None,
    ):
        super().__init__(
            event_id=uuid4(),
            event_type="OrderShipped",
            occurred_at=occurred_at or datetime.utcnow(),
            metadata=metadata,
        )
        self.order_id = order_id
        self.shipment_id = shipment_id
        self.tracking_code = tracking_code
        self.carrier = carrier
