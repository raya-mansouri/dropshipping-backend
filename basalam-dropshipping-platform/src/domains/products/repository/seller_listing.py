"""
SellerListing Repository
=========================
Repository for SellerListing model operations
"""

from typing import Optional, List
import uuid
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import SellerListing


class SellerListingRepository:
    """
    Repository for managing SellerListing entities.

    Handles database operations for seller listings (seller's copy of supplier products)
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize repository with database session.

        Args:
            session: Async SQLAlchemy session
        """
        self.session = session

    async def get_by_id(self, id: uuid.UUID) -> Optional[SellerListing]:
        """
        Get seller listing by its UUID.

        Args:
            id: SellerListing UUID

        Returns:
            SellerListing instance if found, None otherwise
        """
        result = await self.session.execute(
            select(SellerListing).where(SellerListing.id == id)
        )
        return result.scalar_one_or_none()

    async def get_by_seller(self, seller_id: uuid.UUID) -> List[SellerListing]:
        """
        Get all listings for a specific seller/shop.

        Args:
            seller_id: Shop UUID (seller)

        Returns:
            List of SellerListing instances for the seller
        """
        result = await self.session.execute(
            select(SellerListing).where(SellerListing.shop_id == seller_id)
        )
        return list(result.scalars().all())

    async def get_by_supplier_product(
        self, seller_id: uuid.UUID, supplier_product_id: uuid.UUID
    ) -> Optional[SellerListing]:
        """
        Check if a supplier product has already been added by a seller.

        Args:
            seller_id: Shop UUID (seller)
            supplier_product_id: SupplierProduct UUID

        Returns:
            SellerListing instance if found, None otherwise
        """
        result = await self.session.execute(
            select(SellerListing).where(
                SellerListing.shop_id == seller_id,
                SellerListing.supplier_product_id == supplier_product_id,
            )
        )
        return result.scalar_one_or_none()

    async def create(self, data: dict) -> SellerListing:
        """
        Create a new seller listing.

        Args:
            data: Dictionary containing listing fields

        Returns:
            Newly created SellerListing instance
        """
        listing = SellerListing(**data)
        self.session.add(listing)
        await self.session.flush()
        await self.session.refresh(listing)
        return listing

    async def update(self, id: uuid.UUID, data: dict) -> Optional[SellerListing]:
        """
        Update seller listing fields.

        Args:
            id: SellerListing UUID
            data: Dictionary containing fields to update

        Returns:
            Updated SellerListing instance if found, None otherwise
        """
        await self.session.execute(
            update(SellerListing).where(SellerListing.id == id).values(**data)
        )
        await self.session.flush()
        return await self.get_by_id(id)

    async def delete(self, id: uuid.UUID) -> bool:
        """
        Soft delete a listing by setting status to 'disabled'.

        Args:
            id: SellerListing UUID

        Returns:
            True if listing was disabled, False if not found
        """
        result = await self.session.execute(
            update(SellerListing)
            .where(SellerListing.id == id)
            .values(status="disabled")
        )
        await self.session.flush()
        return result.rowcount > 0
