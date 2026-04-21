"""
Shop Integration Repository
===========================
Repository for ShopIntegration model operations, extending BaseRepository.
"""

from typing import Optional, List
import uuid
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repository.base import BaseRepository
from ..models import ShopIntegration

# Statuses that block creating a new integration.
# "pending" is excluded: an abandoned OAuth flow should be overridable.
BLOCKING_STATUSES = {"connected", "error"}

# Enforced at DB level by partial unique index one_active_integration_per_shop
# (migration a1b2c3d4e5f6). Prevents race conditions where concurrent requests
# could both pass the application-level check above.


class ShopIntegrationRepository(BaseRepository[ShopIntegration]):
    """
    Repository for managing ShopIntegration entities.

    Extends BaseRepository for CRUD, QueryBuilder, pagination, and audit trail.
    """

    def __init__(self, session: AsyncSession):
        super().__init__(session, ShopIntegration)

    async def get_by_shop(self, shop_id: uuid.UUID) -> List[ShopIntegration]:
        """Get all integrations for a specific shop."""
        result = await self.session.execute(
            select(ShopIntegration).where(ShopIntegration.shop_id == shop_id)
        )
        return list(result.scalars().all())

    async def get_active_by_shop(self, shop_id: uuid.UUID) -> Optional[ShopIntegration]:
        """Get the integration that blocks new connections for a shop.

        Returns the first integration with status in ('connected', 'error'),
        or None if the shop has no blocking integration.
        A 'pending' integration (abandoned OAuth) does NOT block.
        """
        result = await self.session.execute(
            select(ShopIntegration).where(
                ShopIntegration.shop_id == shop_id,
                ShopIntegration.status.in_(BLOCKING_STATUSES),
            )
        )
        return result.scalar_one_or_none()

    async def get_pending_by_shop(
        self, shop_id: uuid.UUID
    ) -> Optional[ShopIntegration]:
        """Get the pending (in-progress OAuth) integration for a shop."""
        result = await self.session.execute(
            select(ShopIntegration).where(
                ShopIntegration.shop_id == shop_id,
                ShopIntegration.status == "pending",
            )
        )
        return result.scalar_one_or_none()

    async def get_by_platform_shop(
        self, platform_id: uuid.UUID, external_shop_id: str
    ) -> Optional[ShopIntegration]:
        """Get integration by platform and external shop ID."""
        result = await self.session.execute(
            select(ShopIntegration).where(
                ShopIntegration.platform_id == platform_id,
                ShopIntegration.external_shop_id == external_shop_id,
            )
        )
        return result.scalar_one_or_none()

    async def update_status(
        self, id: uuid.UUID, status: str, error: Optional[str] = None
    ) -> Optional[ShopIntegration]:
        """Update integration status and optional error message."""
        values = {"status": status}
        if error is not None:
            values["last_error"] = error

        await self.session.execute(
            update(ShopIntegration).where(ShopIntegration.id == id).values(**values)
        )
        await self.session.flush()
        return await self.get_by_id(id)

    async def delete(self, id: uuid.UUID) -> bool:
        """Hard delete an integration record."""
        instance = await self.get_by_id(id)
        if instance is None:
            return False
        await self.session.delete(instance)
        await self.session.flush()
        return True
