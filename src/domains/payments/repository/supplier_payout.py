"""
Supplier Payout Repository
==========================
Repository for SupplierPayout model operations
"""

from typing import Optional, List
import uuid
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import SupplierPayout


class SupplierPayoutRepository:
    """
    Repository for managing SupplierPayout entities.

    Handles database operations for supplier payout records
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, id: uuid.UUID) -> Optional[SupplierPayout]:
        result = await self.session.execute(
            select(SupplierPayout).where(SupplierPayout.id == id)
        )
        return result.scalar_one_or_none()

    async def get_by_supplier(self, supplier_id: uuid.UUID) -> List[SupplierPayout]:
        result = await self.session.execute(
            select(SupplierPayout)
            .where(SupplierPayout.supplier_id == supplier_id)
            .order_by(SupplierPayout.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_status(self, status: str) -> List[SupplierPayout]:
        result = await self.session.execute(
            select(SupplierPayout)
            .where(SupplierPayout.status == status)
            .order_by(SupplierPayout.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_pending(self) -> List[SupplierPayout]:
        result = await self.session.execute(
            select(SupplierPayout)
            .where(SupplierPayout.status == "pending")
            .where(SupplierPayout.release_conditions_met == True)
            .order_by(SupplierPayout.dispute_window_ends_at.asc())
        )
        return list(result.scalars().all())

    async def create(self, data: dict) -> SupplierPayout:
        payout = SupplierPayout(**data)
        self.session.add(payout)
        await self.session.flush()
        await self.session.refresh(payout)
        return payout

    async def update(self, id: uuid.UUID, data: dict) -> Optional[SupplierPayout]:
        await self.session.execute(
            update(SupplierPayout).where(SupplierPayout.id == id).values(**data)
        )
        await self.session.flush()
        return await self.get_by_id(id)

    async def update_status(
        self, id: uuid.UUID, status: str
    ) -> Optional[SupplierPayout]:
        return await self.update(id, {"status": status})
