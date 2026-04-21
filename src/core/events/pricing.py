from datetime import datetime, timezone
from typing import Dict, Any, Optional
from uuid import UUID, uuid4

from .base import DomainEvent


class PriceUpdated(DomainEvent):
    def __init__(
        self,
        variant_id: UUID,
        old_price: int,
        new_price: int,
        source: str,
        occurred_at: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            event_id=uuid4(),
            event_type="PriceUpdated",
            occurred_at=occurred_at or datetime.now(timezone.utc),
            metadata=metadata or {},
        )
        self.variant_id = variant_id
        self.old_price = old_price
        self.new_price = new_price
        self.source = source


class MarginValidationFailed(DomainEvent):
    def __init__(
        self,
        listing_id: UUID,
        required_margin: float,
        current_margin: float,
        occurred_at: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            event_id=uuid4(),
            event_type="MarginValidationFailed",
            occurred_at=occurred_at or datetime.now(timezone.utc),
            metadata=metadata or {},
        )
        self.listing_id = listing_id
        self.required_margin = required_margin
        self.current_margin = current_margin
