from datetime import datetime
from typing import Dict, Any, Optional
from uuid import UUID
from pydantic import BaseModel


class EventMetadata(BaseModel):
    """Metadata for domain events including event_id, occurred_at, and correlation_id."""

    event_id: UUID
    occurred_at: datetime
    correlation_id: Optional[UUID] = None
    causation_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    tenant_id: Optional[UUID] = None
    version: str = "1.0"
    extra: Dict[str, Any] = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": str(self.event_id),
            "occurred_at": self.occurred_at.isoformat(),
            "correlation_id": str(self.correlation_id) if self.correlation_id else None,
            "causation_id": str(self.causation_id) if self.causation_id else None,
            "user_id": str(self.user_id) if self.user_id else None,
            "tenant_id": str(self.tenant_id) if self.tenant_id else None,
            "version": self.version,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EventMetadata":
        return cls(
            event_id=UUID(data["event_id"]),
            occurred_at=datetime.fromisoformat(data["occurred_at"]),
            correlation_id=UUID(data["correlation_id"])
            if data.get("correlation_id")
            else None,
            causation_id=UUID(data["causation_id"])
            if data.get("causation_id")
            else None,
            user_id=UUID(data["user_id"]) if data.get("user_id") else None,
            tenant_id=UUID(data["tenant_id"]) if data.get("tenant_id") else None,
            version=data.get("version", "1.0"),
            extra=data.get("extra", {}),
        )


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

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DomainEvent":
        return cls(
            event_id=UUID(data["event_id"]),
            event_type=data["event_type"],
            occurred_at=datetime.fromisoformat(data["occurred_at"]),
            metadata=data.get("metadata", {}),
        )
