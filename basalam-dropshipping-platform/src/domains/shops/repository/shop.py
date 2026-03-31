"""
Shop Repository
===============
Repository for Shop model operations, extending BaseRepository.
"""

from typing import List
import uuid
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repository.base import BaseRepository
from ..models import Shop


class ShopRepository(BaseRepository[Shop]):
    """
    Repository for managing Shop entities.

    Extends BaseRepository for CRUD, QueryBuilder, pagination, and audit trail.
    Overrides delete() to soft-delete via status="disabled".
    """

    def __init__(self, session: AsyncSession):
        super().__init__(session, Shop)

    async def get_by_account(self, account_id: uuid.UUID) -> List[Shop]:
        """Get all shops for a specific account."""
        result = await self.session.execute(
            select(Shop).where(Shop.account_id == account_id)
        )
        return list(result.scalars().all())

    async def get_by_role(self, account_id: uuid.UUID, role: str) -> List[Shop]:
        """Get shops by role for a specific account."""
        result = await self.session.execute(
            select(Shop).where(Shop.account_id == account_id, Shop.shop_role == role)
        )
        return list(result.scalars().all())

    async def get_by_role_global(self, role: str) -> List[Shop]:
        """Get all shops with a given role across all accounts."""
        result = await self.session.execute(
            select(Shop).where(Shop.shop_role == role)
        )
        return list(result.scalars().all())

    async def delete(self, id: uuid.UUID) -> bool:
        """Soft delete by setting status to 'disabled'."""
        result = await self.session.execute(
            update(Shop).where(Shop.id == id).values(status="disabled")
        )
        await self.session.flush()
        return result.rowcount > 0
