from datetime import datetime
from typing import Dict, Any
from uuid import UUID, uuid4

from .base import DomainEvent


class InventoryReserved(DomainEvent):
    def __init__(
        self,
        variant_id: UUID,
        order_item_id: UUID,
        quantity: int,
        expires_at: datetime,
        occurred_at: datetime = None,
        metadata: Dict[str, Any] = None,
    ):
        super().__init__(
            event_id=uuid4(),
            event_type="InventoryReserved",
            occurred_at=occurred_at or datetime.utcnow(),
            metadata=metadata,
        )
        self.variant_id = variant_id
        self.order_item_id = order_item_id
        self.quantity = quantity
        self.expires_at = expires_at


class InventoryReleased(DomainEvent):
    def __init__(
        self,
        variant_id: UUID,
        order_item_id: UUID,
        quantity: int,
        reason: str,
        occurred_at: datetime = None,
        metadata: Dict[str, Any] = None,
    ):
        super().__init__(
            event_id=uuid4(),
            event_type="InventoryReleased",
            occurred_at=occurred_at or datetime.utcnow(),
            metadata=metadata,
        )
        self.variant_id = variant_id
        self.order_item_id = order_item_id
        self.quantity = quantity
        self.reason = reason


class InventoryUpdated(DomainEvent):
    def __init__(
        self,
        variant_id: UUID,
        old_quantity: int,
        new_quantity: int,
        source: str,
        occurred_at: datetime = None,
        metadata: Dict[str, Any] = None,
    ):
        super().__init__(
            event_id=uuid4(),
            event_type="InventoryUpdated",
            occurred_at=occurred_at or datetime.utcnow(),
            metadata=metadata,
        )
        self.variant_id = variant_id
        self.old_quantity = old_quantity
        self.new_quantity = new_quantity
        self.source = source


class InventorySyncCompleted(DomainEvent):
    def __init__(
        self,
        integration_id: UUID,
        variants_synced: int,
        errors: list,
        occurred_at: datetime = None,
        metadata: Dict[str, Any] = None,
    ):
        super().__init__(
            event_id=uuid4(),
            event_type="InventorySyncCompleted",
            occurred_at=occurred_at or datetime.utcnow(),
            metadata=metadata,
        )
        self.integration_id = integration_id
        self.variants_synced = variants_synced
        self.errors = errors
