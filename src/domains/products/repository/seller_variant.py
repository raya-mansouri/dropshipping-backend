"""
SellerVariant Repository
========================
Repository for SellerVariant model operations
"""

from typing import Optional, List
import uuid
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import SellerVariant


class SellerVariantRepository:
    """
    Repository for managing SellerVariant entities.

    Handles database operations for seller variants (seller's variant with calculated price)
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize repository with database session.

        Args:
            session: Async SQLAlchemy session
        """
        self.session = session

    async def get_by_id(self, id: uuid.UUID) -> Optional[SellerVariant]:
        """
        Get seller variant by its UUID.

        Args:
            id: SellerVariant UUID

        Returns:
            SellerVariant instance if found, None otherwise
        """
        result = await self.session.execute(
            select(SellerVariant).where(SellerVariant.id == id)
        )
        return result.scalar_one_or_none()

    async def get_by_listing(self, listing_id: uuid.UUID) -> List[SellerVariant]:
        """
        Get all variants for a specific seller listing.

        Args:
            listing_id: SellerListing UUID

        Returns:
            List of SellerVariant instances for the listing
        """
        result = await self.session.execute(
            select(SellerVariant).where(SellerVariant.listing_id == listing_id)
        )
        return list(result.scalars().all())

    async def create(self, data: dict) -> SellerVariant:
        """
        Create a new seller variant.

        Args:
            data: Dictionary containing variant fields

        Returns:
            Newly created SellerVariant instance
        """
        variant = SellerVariant(**data)
        self.session.add(variant)
        await self.session.flush()
        await self.session.refresh(variant)
        return variant

    async def update(self, id: uuid.UUID, data: dict) -> Optional[SellerVariant]:
        """
        Update seller variant fields.

        Args:
            id: SellerVariant UUID
            data: Dictionary containing fields to update

        Returns:
            Updated SellerVariant instance if found, None otherwise
        """
        await self.session.execute(
            update(SellerVariant).where(SellerVariant.id == id).values(**data)
        )
        await self.session.flush()
        return await self.get_by_id(id)
