"""
SupplierVariant Repository
==========================
Repository for SupplierVariant model operations
"""

from typing import Optional, List
import uuid
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import SupplierVariant, SupplierProduct, ProductVariant


class SupplierVariantRepository:
    """
    Repository for managing SupplierVariant entities.

    Handles database operations for supplier-specific variant data
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize repository with database session.

        Args:
            session: Async SQLAlchemy session
        """
        self.session = session

    async def get_by_id(self, id: uuid.UUID) -> Optional[SupplierVariant]:
        """
        Get supplier variant by its UUID.

        Args:
            id: SupplierVariant UUID

        Returns:
            SupplierVariant instance if found, None otherwise
        """
        result = await self.session.execute(
            select(SupplierVariant).where(SupplierVariant.id == id)
        )
        return result.scalar_one_or_none()

    async def get_by_product(self, product_id: uuid.UUID) -> List[SupplierVariant]:
        """
        Get all variants for a specific supplier product.

        Args:
            product_id: SupplierProduct UUID

        Returns:
            List of SupplierVariant instances for the product
        """
        result = await self.session.execute(
            select(SupplierVariant).where(
                SupplierVariant.supplier_product_id == product_id
            )
        )
        return list(result.scalars().all())

    async def get_by_external_id(
        self, shop_id: uuid.UUID, external_id: str
    ) -> Optional[SupplierVariant]:
        """
        Get variant by shop and external variant ID (Basalam variant ID).

        Args:
            shop_id: Shop UUID
            external_id: External variant ID from Basalam

        Returns:
            SupplierVariant instance if found, None otherwise
        """
        result = await self.session.execute(
            select(SupplierVariant)
            .join(
                SupplierProduct,
                SupplierVariant.supplier_product_id == SupplierProduct.id,
            )
            .join(ProductVariant, SupplierVariant.variant_id == ProductVariant.id)
            .where(
                SupplierProduct.shop_id == shop_id,
                ProductVariant.external_variant_id == external_id,
            )
        )
        return result.scalar_one_or_none()

    async def create(self, data: dict) -> SupplierVariant:
        """
        Create a new supplier variant.

        Args:
            data: Dictionary containing variant fields

        Returns:
            Newly created SupplierVariant instance
        """
        variant = SupplierVariant(**data)
        self.session.add(variant)
        await self.session.flush()
        await self.session.refresh(variant)
        return variant

    async def update(self, id: uuid.UUID, data: dict) -> Optional[SupplierVariant]:
        """
        Update supplier variant fields.

        Args:
            id: SupplierVariant UUID
            data: Dictionary containing fields to update

        Returns:
            Updated SupplierVariant instance if found, None otherwise
        """
        await self.session.execute(
            update(SupplierVariant).where(SupplierVariant.id == id).values(**data)
        )
        await self.session.flush()
        return await self.get_by_id(id)
