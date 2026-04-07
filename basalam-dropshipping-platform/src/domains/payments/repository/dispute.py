"""
Dispute Repository
==================
Repository for Dispute model operations
"""

from typing import Optional, List
import uuid
from datetime import datetime, timezone
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Dispute


class DisputeRepository:
    """
    Repository for managing Dispute entities.

    Handles database operations for dispute records
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, id: uuid.UUID) -> Optional[Dispute]:
        result = await self.session.execute(select(Dispute).where(Dispute.id == id))
        return result.scalar_one_or_none()

    async def get_by_order(self, order_item_id: uuid.UUID) -> Optional[Dispute]:
        result = await self.session.execute(
            select(Dispute).where(Dispute.order_item_id == order_item_id)
        )
        return result.scalar_one_or_none()

    async def get_by_status(self, status: str) -> List[Dispute]:
        result = await self.session.execute(
            select(Dispute)
            .where(Dispute.status == status)
            .order_by(Dispute.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_active(self) -> List[Dispute]:
        result = await self.session.execute(
            select(Dispute)
            .where(Dispute.status.in_(["open", "investigating"]))
            .order_by(Dispute.created_at.asc())
        )
        return list(result.scalars().all())

    async def create(self, data: dict) -> Dispute:
        dispute = Dispute(**data)
        self.session.add(dispute)
        await self.session.flush()
        await self.session.refresh(dispute)
        return dispute

    async def update(self, id: uuid.UUID, data: dict) -> Optional[Dispute]:
        await self.session.execute(
            update(Dispute).where(Dispute.id == id).values(**data)
        )
        await self.session.flush()
        return await self.get_by_id(id)

    async def resolve(
        self,
        id: uuid.UUID,
        resolution: str,
        outcome: str,
        resolved_by: uuid.UUID,
        outcome_amount: Optional[float] = None,
    ) -> Optional[Dispute]:
        data = {
            "resolution": resolution,
            "outcome": outcome,
            "resolved_by": resolved_by,
            "resolved_at": datetime.now(timezone.utc),
        }
        if outcome_amount is not None:
            data["outcome_amount"] = outcome_amount
        return await self.update(id, data)
