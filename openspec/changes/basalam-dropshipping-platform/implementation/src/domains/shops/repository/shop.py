"""
Shop Repository
===============
Repository for Shop model operations
"""

from typing import Optional, List
import uuid
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import Base

from ..models import Shop


class ShopRepository:
    """
    Repository for managing Shop entities.

    Handles database operations for shop records (suppliers and sellers)
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize repository with database session.

        Args:
            session: Async SQLAlchemy session
        """
        self.session = session

    async def get_by_id(self, id: uuid.UUID) -> Optional[Shop]:
        """
        Get shop by its UUID.

        Args:
            id: Shop UUID

        Returns:
            Shop instance if found, None otherwise
        """
        result = await self.session.execute(select(Shop).where(Shop.id == id))
        return result.scalar_one_or_none()

    async def get_by_account(self, account_id: uuid.UUID) -> List[Shop]:
        """
        Get all shops for a specific account.

        Args:
            account_id: Account UUID

        Returns:
            List of Shop instances belonging to the account
        """
        result = await self.session.execute(
            select(Shop).where(Shop.account_id == account_id)
        )
        return list(result.scalars().all())

    async def get_by_role(self, account_id: uuid.UUID, role: str) -> List[Shop]:
        """
        Get shops by role for a specific account.

        Args:
            account_id: Account UUID
            role: Shop role ('supplier' or 'seller')

        Returns:
            List of Shop instances with the specified role
        """
        result = await self.session.execute(
            select(Shop).where(Shop.account_id == account_id, Shop.shop_role == role)
        )
        return list(result.scalars().all())

    async def create(self, data: dict) -> Shop:
        """
        Create a new shop.

        Args:
            data: Dictionary containing shop fields

        Returns:
            Newly created Shop instance
        """
        shop = Shop(**data)
        self.session.add(shop)
        await self.session.flush()
        await self.session.refresh(shop)
        return shop

    async def update(self, id: uuid.UUID, data: dict) -> Optional[Shop]:
        """
        Update shop fields.

        Args:
            id: Shop UUID
            data: Dictionary containing fields to update

        Returns:
            Updated Shop instance if found, None otherwise
        """
        await self.session.execute(update(Shop).where(Shop.id == id).values(**data))
        await self.session.flush()
        return await self.get_by_id(id)

    async def delete(self, id: uuid.UUID) -> bool:
        """
        Soft delete a shop by setting status to 'disabled'.

        Args:
            id: Shop UUID

        Returns:
            True if shop was disabled, False if not found
        """
        result = await self.session.execute(
            update(Shop).where(Shop.id == id).values(status="disabled")
        )
        await self.session.flush()
        return result.rowcount > 0
