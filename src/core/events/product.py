from datetime import datetime, timezone
from typing import Dict, Any, Optional
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


class ProductSyncRequested(DomainEvent):
    """Published to trigger a product sync for a specific integration."""

    def __init__(
        self,
        integration_id: "str | UUID",
        full_sync: bool = False,
        triggered_by: str = "manual",
        job_id: "Optional[str | UUID]" = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        if not integration_id:
            raise ValueError("integration_id is required")

        # Auto-coerce str to UUID so both publishers and consumers work
        if isinstance(integration_id, str):
            integration_id = UUID(integration_id)
        if job_id is not None and isinstance(job_id, str):
            job_id = UUID(job_id)

        self.integration_id = integration_id
        self.full_sync = full_sync
        self.triggered_by = triggered_by
        self.job_id = job_id

        meta = dict(metadata) if metadata else {}
        meta.update(
            {
                "integration_id": str(integration_id),
                "full_sync": full_sync,
                "triggered_by": triggered_by,
            }
        )
        if job_id is not None:
            meta["job_id"] = str(job_id)
        super().__init__(
            event_id=uuid4(),
            event_type="ProductSyncRequested",
            occurred_at=datetime.now(timezone.utc),
            metadata=meta,
        )
