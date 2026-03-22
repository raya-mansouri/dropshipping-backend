"""
Shop Integration Repository
===========================
Repository for ShopIntegration model operations
"""

from typing import Optional, List
import uuid
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import Base

from ..models import ShopIntegration


class ShopIntegrationRepository:
    """
    Repository for managing ShopIntegration entities.

    Handles database operations for shop integration records
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize repository with database session.

        Args:
            session: Async SQLAlchemy session
        """
        self.session = session

    async def get_by_id(self, id: uuid.UUID) -> Optional[ShopIntegration]:
        """
        Get integration by its UUID.

        Args:
            id: Integration UUID

        Returns:
            ShopIntegration instance if found, None otherwise
        """
        result = await self.session.execute(
            select(ShopIntegration).where(ShopIntegration.id == id)
        )
        return result.scalar_one_or_none()

    async def get_by_shop(self, shop_id: uuid.UUID) -> List[ShopIntegration]:
        """
        Get all integrations for a specific shop.

        Args:
            shop_id: Shop UUID

        Returns:
            List of ShopIntegration instances for the shop
        """
        result = await self.session.execute(
            select(ShopIntegration).where(ShopIntegration.shop_id == shop_id)
        )
        return list(result.scalars().all())

    async def get_by_platform_shop(
        self, platform_id: uuid.UUID, external_shop_id: str
    ) -> Optional[ShopIntegration]:
        """
        Get integration by platform and external shop ID.

        Args:
            platform_id: Platform UUID
            external_shop_id: External shop ID on the platform

        Returns:
            ShopIntegration instance if found, None otherwise
        """
        result = await self.session.execute(
            select(ShopIntegration).where(
                ShopIntegration.platform_id == platform_id,
                ShopIntegration.external_shop_id == external_shop_id,
            )
        )
        return result.scalar_one_or_none()

    async def create(self, data: dict) -> ShopIntegration:
        """
        Create a new integration.

        Args:
            data: Dictionary containing integration fields

        Returns:
            Newly created ShopIntegration instance
        """
        integration = ShopIntegration(**data)
        self.session.add(integration)
        await self.session.flush()
        await self.session.refresh(integration)
        return integration

    async def update(self, id: uuid.UUID, data: dict) -> Optional[ShopIntegration]:
        """
        Update integration fields.

        Args:
            id: Integration UUID
            data: Dictionary containing fields to update

        Returns:
            Updated ShopIntegration instance if found, None otherwise
        """
        await self.session.execute(
            update(ShopIntegration).where(ShopIntegration.id == id).values(**data)
        )
        await self.session.flush()
        return await self.get_by_id(id)

    async def update_status(
        self, id: uuid.UUID, status: str, error: Optional[str] = None
    ) -> Optional[ShopIntegration]:
        """
        Update integration status and optional error message.

        Args:
            id: Integration UUID
            status: New status ('connected', 'disconnected', 'error')
            error: Optional error message

        Returns:
            Updated ShopIntegration instance if found, None otherwise
        """
        values = {"status": status}
        if error is not None:
            values["last_error"] = error

        await self.session.execute(
            update(ShopIntegration).where(ShopIntegration.id == id).values(**values)
        )
        await self.session.flush()
        return await self.get_by_id(id)
