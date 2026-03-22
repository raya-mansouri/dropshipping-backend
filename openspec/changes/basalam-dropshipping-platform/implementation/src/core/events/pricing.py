from datetime import datetime
from typing import Dict, Any
from uuid import UUID, uuid4

from .base import DomainEvent


class PriceUpdated(DomainEvent):
    def __init__(
        self,
        variant_id: UUID,
        old_price: float,
        new_price: float,
        source: str,
        occurred_at: datetime = None,
        metadata: Dict[str, Any] = None,
    ):
        super().__init__(
            event_id=uuid4(),
            event_type="PriceUpdated",
            occurred_at=occurred_at or datetime.utcnow(),
            metadata=metadata,
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
        occurred_at: datetime = None,
        metadata: Dict[str, Any] = None,
    ):
        super().__init__(
            event_id=uuid4(),
            event_type="MarginValidationFailed",
            occurred_at=occurred_at or datetime.utcnow(),
            metadata=metadata,
        )
        self.listing_id = listing_id
        self.required_margin = required_margin
        self.current_margin = current_margin
