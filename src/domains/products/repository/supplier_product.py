"""
SupplierProduct Repository
==========================
Repository for SupplierProduct model operations
"""

from typing import Optional, List, Dict, Any
import uuid
from sqlalchemy import select, update, or_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import SupplierProduct


class SupplierProductRepository:
    """
    Repository for managing SupplierProduct entities.

    Handles database operations for supplier products (from Basalam)
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize repository with database session.

        Args:
            session: Async SQLAlchemy session
        """
        self.session = session

    async def get_by_id(self, id: uuid.UUID) -> Optional[SupplierProduct]:
        """
        Get supplier product by its UUID.

        Args:
            id: SupplierProduct UUID

        Returns:
            SupplierProduct instance if found, None otherwise
        """
        result = await self.session.execute(
            select(SupplierProduct).where(SupplierProduct.id == id)
        )
        return result.scalar_one_or_none()

    async def get_by_shop(self, shop_id: uuid.UUID) -> List[SupplierProduct]:
        """
        Get all products for a specific shop/supplier.

        Args:
            shop_id: Shop UUID

        Returns:
            List of SupplierProduct instances for the shop
        """
        result = await self.session.execute(
            select(SupplierProduct).where(SupplierProduct.shop_id == shop_id)
        )
        return list(result.scalars().all())

    async def get_by_external_id(
        self, shop_id: uuid.UUID, external_id: str
    ) -> Optional[SupplierProduct]:
        """
        Get product by shop and external product ID (Basalam product ID).

        Args:
            shop_id: Shop UUID
            external_id: External product ID from Basalam

        Returns:
            SupplierProduct instance if found, None otherwise
        """
        result = await self.session.execute(
            select(SupplierProduct).where(
                SupplierProduct.shop_id == shop_id,
                SupplierProduct.external_product_id == external_id,
            )
        )
        return result.scalar_one_or_none()

    async def search(
        self, query: str, filters: Optional[Dict[str, Any]] = None
    ) -> List[SupplierProduct]:
        """
        Search products with optional filters.

        Args:
            query: Search query string (searches title and description)
            filters: Optional filters (shop_id, status, category_id, has_variants)

        Returns:
            List of matching SupplierProduct instances
        """
        stmt = select(SupplierProduct)

        if query:
            search_pattern = f"%{query}%"
            stmt = stmt.where(
                or_(
                    SupplierProduct.title.ilike(search_pattern),
                    SupplierProduct.description.ilike(search_pattern),
                )
            )

        if filters:
            if "shop_id" in filters:
                stmt = stmt.where(SupplierProduct.shop_id == filters["shop_id"])
            if "status" in filters:
                stmt = stmt.where(SupplierProduct.status == filters["status"])
            if "category_id" in filters:
                stmt = stmt.where(SupplierProduct.category_id == filters["category_id"])
            if "has_variants" in filters:
                stmt = stmt.where(
                    SupplierProduct.has_variants == filters["has_variants"]
                )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, data: dict) -> SupplierProduct:
        """
        Create a new supplier product.

        Args:
            data: Dictionary containing product fields

        Returns:
            Newly created SupplierProduct instance
        """
        product = SupplierProduct(**data)
        self.session.add(product)
        await self.session.flush()
        await self.session.refresh(product)
        return product

    async def update(self, id: uuid.UUID, data: dict) -> Optional[SupplierProduct]:
        """
        Update supplier product fields.

        Args:
            id: SupplierProduct UUID
            data: Dictionary containing fields to update

        Returns:
            Updated SupplierProduct instance if found, None otherwise
        """
        await self.session.execute(
            update(SupplierProduct).where(SupplierProduct.id == id).values(**data)
        )
        await self.session.flush()
        return await self.get_by_id(id)

    async def delete(self, id: uuid.UUID) -> bool:
        """
        Soft delete a product by setting status to 'archived'.

        Args:
            id: SupplierProduct UUID

        Returns:
            True if product was archived, False if not found
        """
        result = await self.session.execute(
            update(SupplierProduct)
            .where(SupplierProduct.id == id)
            .values(status="archived")
        )
        await self.session.flush()
        return result.rowcount > 0
