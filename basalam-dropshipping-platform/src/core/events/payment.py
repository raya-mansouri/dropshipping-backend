from datetime import datetime
from typing import Dict, Any
from uuid import UUID, uuid4

from .base import DomainEvent


class PaymentReceived(DomainEvent):
    def __init__(
        self,
        order_id: UUID,
        payment_id: UUID,
        amount: float,
        gateway: str,
        occurred_at: datetime = None,
        metadata: Dict[str, Any] = None,
    ):
        super().__init__(
            event_id=uuid4(),
            event_type="PaymentReceived",
            occurred_at=occurred_at or datetime.utcnow(),
            metadata=metadata,
        )
        self.order_id = order_id
        self.payment_id = payment_id
        self.amount = amount
        self.gateway = gateway


class PaymentToEscrow(DomainEvent):
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
            event_type="PaymentToEscrow",
            occurred_at=occurred_at or datetime.utcnow(),
            metadata=metadata,
        )
        self.order_id = order_id
        self.payment_id = payment_id
        self.amount = amount


class PaymentReleasedToSupplier(DomainEvent):
    def __init__(
        self,
        order_id: UUID,
        payment_id: UUID,
        supplier_id: UUID,
        amount: float,
        occurred_at: datetime = None,
        metadata: Dict[str, Any] = None,
    ):
        super().__init__(
            event_id=uuid4(),
            event_type="PaymentReleasedToSupplier",
            occurred_at=occurred_at or datetime.utcnow(),
            metadata=metadata,
        )
        self.order_id = order_id
        self.payment_id = payment_id
        self.supplier_id = supplier_id
        self.amount = amount


class RefundInitiated(DomainEvent):
    def __init__(
        self,
        payment_id: UUID,
        order_item_id: UUID,
        amount: float,
        reason: str,
        occurred_at: datetime = None,
        metadata: Dict[str, Any] = None,
    ):
        super().__init__(
            event_id=uuid4(),
            event_type="RefundInitiated",
            occurred_at=occurred_at or datetime.utcnow(),
            metadata=metadata,
        )
        self.payment_id = payment_id
        self.order_item_id = order_item_id
        self.amount = amount
        self.reason = reason


class RefundCompleted(DomainEvent):
    def __init__(
        self,
        refund_id: UUID,
        payment_id: UUID,
        order_item_id: UUID,
        amount: float,
        occurred_at: datetime = None,
        metadata: Dict[str, Any] = None,
    ):
        super().__init__(
            event_id=uuid4(),
            event_type="RefundCompleted",
            occurred_at=occurred_at or datetime.utcnow(),
            metadata=metadata,
        )
        self.refund_id = refund_id
        self.payment_id = payment_id
        self.order_item_id = order_item_id
        self.amount = amount
