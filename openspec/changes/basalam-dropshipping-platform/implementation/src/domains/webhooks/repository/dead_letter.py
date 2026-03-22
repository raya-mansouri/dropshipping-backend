"""
Webhook Dead Letter Repository
==============================
Repository for WebhookDeadLetter model operations
"""

from typing import Optional, List
import uuid
from datetime import datetime
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import WebhookDeadLetter, WebhookEvent


class WebhookDeadLetterRepository:
    """
    Repository for managing WebhookDeadLetter entities.

    Handles dead letter queue operations for failed webhook events
    that require manual intervention.
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize repository with database session.

        Args:
            session: Async SQLAlchemy session
        """
        self.session = session

    async def get_by_id(self, id: uuid.UUID) -> Optional[WebhookDeadLetter]:
        """
        Get dead letter record by its UUID.

        Args:
            id: WebhookDeadLetter UUID

        Returns:
            WebhookDeadLetter instance if found, None otherwise
        """
        result = await self.session.execute(
            select(WebhookDeadLetter).where(WebhookDeadLetter.id == id)
        )
        return result.scalar_one_or_none()

    async def get_by_event_id(
        self, webhook_event_id: uuid.UUID
    ) -> Optional[WebhookDeadLetter]:
        """
        Get dead letter record by webhook event ID.

        Args:
            webhook_event_id: WebhookEvent UUID

        Returns:
            WebhookDeadLetter instance if found, None otherwise
        """
        result = await self.session.execute(
            select(WebhookDeadLetter).where(
                WebhookDeadLetter.webhook_event_id == webhook_event_id
            )
        )
        return result.scalar_one_or_none()

    async def get_all(
        self, limit: int = 100, offset: int = 0
    ) -> List[WebhookDeadLetter]:
        """
        Get all dead letter records with pagination.

        Args:
            limit: Maximum number of results
            offset: Number of records to skip

        Returns:
            List of WebhookDeadLetter instances
        """
        result = await self.session.execute(
            select(WebhookDeadLetter)
            .order_by(WebhookDeadLetter.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_by_status(
        self, status: str, limit: int = 100
    ) -> List[WebhookDeadLetter]:
        """
        Get dead letter records by status.

        Args:
            status: Status to filter by ('pending', 'investigation', 'resolved')
            limit: Maximum number of results

        Returns:
            List of WebhookDeadLetter instances with the status
        """
        result = await self.session.execute(
            select(WebhookDeadLetter)
            .where(WebhookDeadLetter.status == status)
            .order_by(WebhookDeadLetter.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_pending(self, limit: int = 100) -> List[WebhookDeadLetter]:
        """
        Get all pending dead letter records.

        Args:
            limit: Maximum number of results

        Returns:
            List of pending WebhookDeadLetter instances
        """
        return await self.get_by_status("pending", limit)

    async def create(self, data: dict) -> WebhookDeadLetter:
        """
        Move a failed webhook event to the dead letter queue.

        Args:
            data: Dictionary containing dead letter fields
                  Must include: webhook_event_id, failure_reason

        Returns:
            Newly created WebhookDeadLetter instance
        """
        event_id = data.get("webhook_event_id")

        if event_id:
            event_result = await self.session.execute(
                select(WebhookEvent).where(WebhookEvent.id == event_id)
            )
            event = event_result.scalar_one_or_none()
            if event:
                data.setdefault("original_event_type", event.event_type)
                data.setdefault("payload", event.payload)

        data.setdefault("failure_count", data.get("failure_count", 0))
        data.setdefault("status", "pending")

        dead_letter = WebhookDeadLetter(**data)
        self.session.add(dead_letter)
        await self.session.flush()
        await self.session.refresh(dead_letter)
        return dead_letter

    async def retry(self, id: uuid.UUID) -> Optional[WebhookDeadLetter]:
        """
        Retry a webhook event from the dead letter queue.

        Marks the dead letter as resolved and updates the original
        webhook event status to 'received' for reprocessing.

        Args:
            id: WebhookDeadLetter UUID

        Returns:
            Updated WebhookDeadLetter instance if found, None otherwise
        """
        dead_letter = await self.get_by_id(id)
        if not dead_letter:
            return None

        await self.session.execute(
            update(WebhookEvent)
            .where(WebhookEvent.id == dead_letter.webhook_event_id)
            .values(
                status="received",
                retry_count=0,
                error_message=None,
                error_trace=None,
                processed_at=None,
            )
        )

        await self.session.execute(
            update(WebhookDeadLetter)
            .where(WebhookDeadLetter.id == id)
            .values(
                status="resolved",
                resolution_notes="Retried for reprocessing",
            )
        )

        await self.session.flush()
        return await self.get_by_id(id)

    async def mark_investigation(self, id: uuid.UUID) -> Optional[WebhookDeadLetter]:
        """
        Mark dead letter as under investigation.

        Args:
            id: WebhookDeadLetter UUID

        Returns:
            Updated WebhookDeadLetter instance if found, None otherwise
        """
        await self.session.execute(
            update(WebhookDeadLetter)
            .where(WebhookDeadLetter.id == id)
            .values(status="investigation")
        )
        await self.session.flush()
        return await self.get_by_id(id)

    async def mark_resolved(
        self, id: uuid.UUID, notes: str, resolved_by: uuid.UUID = None
    ) -> Optional[WebhookDeadLetter]:
        """
        Mark dead letter as resolved.

        Args:
            id: WebhookDeadLetter UUID
            notes: Resolution notes
            resolved_by: UUID of user who resolved it

        Returns:
            Updated WebhookDeadLetter instance if found, None otherwise
        """
        await self.session.execute(
            update(WebhookDeadLetter)
            .where(WebhookDeadLetter.id == id)
            .values(
                status="resolved",
                resolution_notes=notes,
                resolved_by=resolved_by,
            )
        )
        await self.session.flush()
        return await self.get_by_id(id)

    async def update(self, id: uuid.UUID, data: dict) -> Optional[WebhookDeadLetter]:
        """
        Update dead letter fields.

        Args:
            id: WebhookDeadLetter UUID
            data: Dictionary containing fields to update

        Returns:
            Updated WebhookDeadLetter instance if found, None otherwise
        """
        await self.session.execute(
            update(WebhookDeadLetter).where(WebhookDeadLetter.id == id).values(**data)
        )
        await self.session.flush()
        return await self.get_by_id(id)

    async def delete(self, id: uuid.UUID) -> bool:
        """
        Delete a dead letter record.

        Args:
            id: WebhookDeadLetter UUID

        Returns:
            True if record was deleted, False if not found
        """
        result = await self.session.execute(
            select(WebhookDeadLetter).where(WebhookDeadLetter.id == id)
        )
        dead_letter = result.scalar_one_or_none()
        if dead_letter:
            await self.session.delete(dead_letter)
            await self.session.flush()
            return True
        return False
