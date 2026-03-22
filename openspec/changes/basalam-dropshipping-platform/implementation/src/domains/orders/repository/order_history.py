"""
OrderHistory Repository
=======================
Repository for OrderHistory model operations
"""

from typing import List
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import OrderHistory


class OrderHistoryRepository:
    """
    Repository for managing OrderHistory entities.

    Handles database operations for order history records (audit trail)
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_order(self, order_id: uuid.UUID) -> List[OrderHistory]:
        result = await self.session.execute(
            select(OrderHistory)
            .where(OrderHistory.order_id == order_id)
            .order_by(OrderHistory.created_at.asc())
        )
        return list(result.scalars().all())

    async def create(self, data: dict) -> OrderHistory:
        history = OrderHistory(**data)
        self.session.add(history)
        await self.session.flush()
        await self.session.refresh(history)
        return history
