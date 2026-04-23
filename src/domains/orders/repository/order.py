"""
Order Repository
================
Repository for Order model operations
"""

from typing import Optional, List
import uuid
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Order, OrderStatus


class OrderRepository:
    """
    Repository for managing Order entities.

    Handles database operations for order records
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, id: uuid.UUID) -> Optional[Order]:
        result = await self.session.execute(select(Order).where(Order.id == id))
        return result.scalar_one_or_none()

    async def get_by_shop(self, shop_id: uuid.UUID, limit: int = 100) -> List[Order]:
        result = await self.session.execute(
            select(Order)
            .where(Order.shop_id == shop_id)
            .order_by(Order.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_external_id(
        self, shop_id: uuid.UUID, external_id: str
    ) -> Optional[Order]:
        result = await self.session.execute(
            select(Order).where(
                Order.shop_id == shop_id, Order.external_order_id == external_id
            )
        )
        return result.scalar_one_or_none()

    async def get_by_status(self, status: OrderStatus, limit: int = 100) -> List[Order]:
        result = await self.session.execute(
            select(Order)
            .where(Order.status == status.value)
            .order_by(Order.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_pending_shipment(self, limit: int = 100) -> List[Order]:
        result = await self.session.execute(
            select(Order)
            .where(Order.status == OrderStatus.PAID.value)
            .order_by(Order.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_orders(
        self,
        shop_ids: Optional[List[uuid.UUID]] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Order]:
        """List orders with optional shop_ids and status filters, with SQL-level pagination."""
        stmt = select(Order)

        if shop_ids is not None:
            stmt = stmt.where(Order.shop_id.in_(shop_ids))

        if status is not None:
            stmt = stmt.where(Order.status == status)

        stmt = stmt.order_by(Order.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, data: dict) -> Order:
        order = Order(**data)
        self.session.add(order)
        await self.session.flush()
        await self.session.refresh(order)
        return order

    async def update(self, id: uuid.UUID, data: dict) -> Optional[Order]:
        await self.session.execute(update(Order).where(Order.id == id).values(**data))
        await self.session.flush()
        return await self.get_by_id(id)

    async def update_status(
        self, id: uuid.UUID, status: OrderStatus
    ) -> Optional[Order]:
        return await self.update(id, {"status": status.value})
