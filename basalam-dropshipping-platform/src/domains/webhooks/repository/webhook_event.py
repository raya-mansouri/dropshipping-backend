"""
Webhook Event Repository
=========================
Repository for WebhookEvent model operations
"""

from typing import Optional, List
import uuid
from datetime import datetime, timezone
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import WebhookEvent, WebhookEventStatus


class WebhookEventRepository:
    """
    Repository for managing WebhookEvent entities.

    Handles database operations for incoming webhook events,
    including creation, status updates, and queries by various criteria.
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize repository with database session.

        Args:
            session: Async SQLAlchemy session
        """
        self.session = session

    async def get_by_id(self, id: uuid.UUID) -> Optional[WebhookEvent]:
        """
        Get webhook event by its UUID.

        Args:
            id: WebhookEvent UUID

        Returns:
            WebhookEvent instance if found, None otherwise
        """
        result = await self.session.execute(
            select(WebhookEvent).where(WebhookEvent.id == id)
        )
        return result.scalar_one_or_none()

    async def get_by_event_type(self, event_type: str) -> List[WebhookEvent]:
        """
        Get all webhook events for a specific event type.

        Args:
            event_type: Event type (e.g., 'order.created', 'product.updated')

        Returns:
            List of WebhookEvent instances matching the event type
        """
        result = await self.session.execute(
            select(WebhookEvent)
            .where(WebhookEvent.event_type == event_type)
            .order_by(WebhookEvent.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_shop(self, shop_id: uuid.UUID) -> List[WebhookEvent]:
        """
        Get all webhook events for a specific shop/integration.

        Args:
            shop_id: Shop UUID

        Returns:
            List of WebhookEvent instances for the shop
        """
        result = await self.session.execute(
            select(WebhookEvent)
            .where(WebhookEvent.integration_id == shop_id)
            .order_by(WebhookEvent.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_platform(self, platform_id: uuid.UUID) -> List[WebhookEvent]:
        """
        Get all webhook events for a specific platform.

        Args:
            platform_id: Platform UUID

        Returns:
            List of WebhookEvent instances for the platform
        """
        result = await self.session.execute(
            select(WebhookEvent)
            .where(WebhookEvent.platform_id == platform_id)
            .order_by(WebhookEvent.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_status(
        self, status: WebhookEventStatus, limit: int = 100
    ) -> List[WebhookEvent]:
        """
        Get webhook events by status.

        Args:
            status: WebhookEventStatus enum value
            limit: Maximum number of results

        Returns:
            List of WebhookEvent instances with the specified status
        """
        result = await self.session.execute(
            select(WebhookEvent)
            .where(WebhookEvent.status == status.value)
            .order_by(WebhookEvent.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def create(self, data: dict) -> WebhookEvent:
        """
        Create a new webhook event.

        Args:
            data: Dictionary containing webhook event fields

        Returns:
            Newly created WebhookEvent instance
        """
        event = WebhookEvent(**data)
        self.session.add(event)
        await self.session.flush()
        await self.session.refresh(event)
        return event

    async def update_status(
        self, id: uuid.UUID, status: WebhookEventStatus
    ) -> Optional[WebhookEvent]:
        """
        Update webhook event status.

        Args:
            id: WebhookEvent UUID
            status: New status from WebhookEventStatus enum

        Returns:
            Updated WebhookEvent instance if found, None otherwise
        """
        update_data = {"status": status.value}

        if status == WebhookEventStatus.COMPLETED:
            update_data["processed_at"] = datetime.now(timezone.utc)

        await self.session.execute(
            update(WebhookEvent).where(WebhookEvent.id == id).values(**update_data)
        )
        await self.session.flush()
        return await self.get_by_id(id)

    async def update(self, id: uuid.UUID, data: dict) -> Optional[WebhookEvent]:
        """
        Update webhook event fields.

        Args:
            id: WebhookEvent UUID
            data: Dictionary containing fields to update

        Returns:
            Updated WebhookEvent instance if found, None otherwise
        """
        await self.session.execute(
            update(WebhookEvent).where(WebhookEvent.id == id).values(**data)
        )
        await self.session.flush()
        return await self.get_by_id(id)

    async def increment_retry(self, id: uuid.UUID) -> Optional[WebhookEvent]:
        """
        Increment retry count for a webhook event.

        Args:
            id: WebhookEvent UUID

        Returns:
            Updated WebhookEvent instance if found, None otherwise
        """
        result = await self.session.execute(
            update(WebhookEvent)
            .where(WebhookEvent.id == id)
            .values(retry_count=WebhookEvent.retry_count + 1)
            .returning(WebhookEvent)
        )
        await self.session.flush()
        return result.scalar_one_or_none()

    async def mark_failed(
        self, id: uuid.UUID, error_message: str, error_trace: str = None
    ) -> Optional[WebhookEvent]:
        """
        Mark webhook event as failed with error details.

        Args:
            id: WebhookEvent UUID
            error_message: Error message describing the failure
            error_trace: Optional error traceback

        Returns:
            Updated WebhookEvent instance if found, None otherwise
        """
        await self.session.execute(
            update(WebhookEvent)
            .where(WebhookEvent.id == id)
            .values(
                status=WebhookEventStatus.FAILED.value,
                error_message=error_message,
                error_trace=error_trace,
                processed_at=datetime.now(timezone.utc),
            )
        )
        await self.session.flush()
        return await self.get_by_id(id)
