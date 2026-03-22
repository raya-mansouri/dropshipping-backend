"""
OrderItem Repository
====================
Repository for OrderItem model operations
"""

from typing import Optional, List
import uuid
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import OrderItem


class OrderItemRepository:
    """
    Repository for managing OrderItem entities.

    Handles database operations for order item records
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, id: uuid.UUID) -> Optional[OrderItem]:
        result = await self.session.execute(select(OrderItem).where(OrderItem.id == id))
        return result.scalar_one_or_none()

    async def get_by_order(self, order_id: uuid.UUID) -> List[OrderItem]:
        result = await self.session.execute(
            select(OrderItem).where(OrderItem.order_id == order_id)
        )
        return list(result.scalars().all())

    async def create(self, data: dict) -> OrderItem:
        item = OrderItem(**data)
        self.session.add(item)
        await self.session.flush()
        await self.session.refresh(item)
        return item

    async def update(self, id: uuid.UUID, data: dict) -> Optional[OrderItem]:
        await self.session.execute(
            update(OrderItem).where(OrderItem.id == id).values(**data)
        )
        await self.session.flush()
        return await self.get_by_id(id)
