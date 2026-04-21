"""
Pricing Repository
==================
Repository for price history data access
"""
from typing import Optional, List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import PriceHistory


class PricingRepository:
    """
    Repository for managing PriceHistory entities.

    Handles database operations for price history records.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, id: UUID) -> Optional[PriceHistory]:
        """Get a price history record by ID."""
        result = await self.session.execute(
            select(PriceHistory).where(PriceHistory.id == id)
        )
        return result.scalar_one_or_none()

    async def get_by_variant(
        self, variant_id: UUID, limit: int = 50
    ) -> List[PriceHistory]:
        """Get price history for a variant, most recent first."""
        result = await self.session.execute(
            select(PriceHistory)
            .where(PriceHistory.variant_id == variant_id)
            .order_by(PriceHistory.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_latest(self, variant_id: UUID) -> Optional[PriceHistory]:
        """Get the most recent price record for a variant."""
        result = await self.session.execute(
            select(PriceHistory)
            .where(PriceHistory.variant_id == variant_id)
            .order_by(PriceHistory.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create(self, data: dict) -> PriceHistory:
        """Create a new price history record."""
        price_history = PriceHistory(**data)
        self.session.add(price_history)
        await self.session.flush()
        await self.session.refresh(price_history)
        return price_history
