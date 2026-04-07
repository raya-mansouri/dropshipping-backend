from datetime import datetime, timezone
from typing import Dict, Any
from uuid import UUID, uuid4

from .base import DomainEvent


class ProductCreated(DomainEvent):
    def __init__(
        self,
        product_id: UUID,
        shop_id: UUID,
        title: str,
        occurred_at: datetime = None,
        metadata: Dict[str, Any] = None,
    ):
        super().__init__(
            event_id=uuid4(),
            event_type="ProductCreated",
            occurred_at=occurred_at or datetime.now(timezone.utc),
            metadata=metadata,
        )
        self.product_id = product_id
        self.shop_id = shop_id
        self.title = title


class ProductUpdated(DomainEvent):
    def __init__(
        self,
        product_id: UUID,
        changes: Dict[str, Any],
        occurred_at: datetime = None,
        metadata: Dict[str, Any] = None,
    ):
        super().__init__(
            event_id=uuid4(),
            event_type="ProductUpdated",
            occurred_at=occurred_at or datetime.now(timezone.utc),
            metadata=metadata,
        )
        self.product_id = product_id
        self.changes = changes


class ProductStatusChanged(DomainEvent):
    def __init__(
        self,
        product_id: UUID,
        old_status: str,
        new_status: str,
        occurred_at: datetime = None,
        metadata: Dict[str, Any] = None,
    ):
        super().__init__(
            event_id=uuid4(),
            event_type="ProductStatusChanged",
            occurred_at=occurred_at or datetime.now(timezone.utc),
            metadata=metadata,
        )
        self.product_id = product_id
        self.old_status = old_status
        self.new_status = new_status


class ProductForbid(DomainEvent):
    def __init__(
        self,
        product_id: UUID,
        reason: str,
        validation_errors: list,
        occurred_at: datetime = None,
        metadata: Dict[str, Any] = None,
    ):
        super().__init__(
            event_id=uuid4(),
            event_type="ProductForbid",
            occurred_at=occurred_at or datetime.now(timezone.utc),
            metadata=metadata,
        )
        self.product_id = product_id
        self.reason = reason
        self.validation_errors = validation_errors


class ProductSynced(DomainEvent):
    def __init__(
        self,
        product_id: UUID,
        basalam_product_id: UUID,
        occurred_at: datetime = None,
        metadata: Dict[str, Any] = None,
    ):
        super().__init__(
            event_id=uuid4(),
            event_type="ProductSynced",
            occurred_at=occurred_at or datetime.now(timezone.utc),
            metadata=metadata,
        )
        self.product_id = product_id
        self.basalam_product_id = basalam_product_id
