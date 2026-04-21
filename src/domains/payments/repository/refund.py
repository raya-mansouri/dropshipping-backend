"""
Refund Repository
=================
Repository for Refund model operations
"""

from typing import Optional, List
import uuid
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Refund


class RefundRepository:
    """
    Repository for managing Refund entities.

    Handles database operations for refund records
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, id: uuid.UUID) -> Optional[Refund]:
        result = await self.session.execute(select(Refund).where(Refund.id == id))
        return result.scalar_one_or_none()

    async def get_by_payment(self, payment_id: uuid.UUID) -> List[Refund]:
        result = await self.session.execute(
            select(Refund)
            .where(Refund.payment_id == payment_id)
            .order_by(Refund.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_order(self, order_item_id: uuid.UUID) -> List[Refund]:
        result = await self.session.execute(
            select(Refund)
            .where(Refund.order_item_id == order_item_id)
            .order_by(Refund.created_at.desc())
        )
        return list(result.scalars().all())

    async def create(self, data: dict) -> Refund:
        refund = Refund(**data)
        self.session.add(refund)
        await self.session.flush()
        await self.session.refresh(refund)
        return refund

    async def update(self, id: uuid.UUID, data: dict) -> Optional[Refund]:
        await self.session.execute(update(Refund).where(Refund.id == id).values(**data))
        await self.session.flush()
        return await self.get_by_id(id)
