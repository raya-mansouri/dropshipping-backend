from datetime import datetime
from typing import Dict, Any
from uuid import UUID


class DomainEvent:
    def __init__(
        self,
        event_id: UUID,
        event_type: str,
        occurred_at: datetime,
        metadata: Dict[str, Any] = None,
    ):
        self.event_id = event_id
        self.event_type = event_type
        self.occurred_at = occurred_at
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": str(self.event_id),
            "event_type": self.event_type,
            "occurred_at": self.occurred_at.isoformat(),
            "metadata": self.metadata,
        }
