"""
Inventory Repository
===================
Repository for Inventory model operations

Note: Inventory is stored in SupplierVariant (products domain)
"""

from typing import Optional, List
import uuid
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.products.models import SupplierVariant


class InventoryRepository:
    """
    Repository for managing inventory operations on SupplierVariant.

    Handles database operations for inventory management including
    reservations, locking, and quantity updates.
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize repository with database session.

        Args:
            session: Async SQLAlchemy session
        """
        self.session = session

    async def get_by_variant_id(
        self, variant_id: uuid.UUID
    ) -> Optional[SupplierVariant]:
        """
        Get inventory for a specific variant.

        Args:
            variant_id: SupplierVariant UUID

        Returns:
            SupplierVariant instance if found, None otherwise
        """
        result = await self.session.execute(
            select(SupplierVariant).where(SupplierVariant.id == variant_id)
        )
        return result.scalar_one_or_none()

    async def get_by_shop(self, shop_id: uuid.UUID) -> List[SupplierVariant]:
        """
        Get all inventory for a shop.

        Args:
            shop_id: Shop UUID

        Returns:
            List of SupplierVariant instances with inventory for the shop
        """
        from src.domains.products.models import SupplierProduct

        result = await self.session.execute(
            select(SupplierVariant)
            .join(
                SupplierProduct,
                SupplierVariant.supplier_product_id == SupplierProduct.id,
            )
            .where(SupplierProduct.shop_id == shop_id)
            .order_by(SupplierVariant.updated_at.desc())
        )
        return list(result.scalars().all())

    async def lock_for_update(self, variant_id: uuid.UUID) -> Optional[SupplierVariant]:
        """
        Lock inventory row for update (SELECT FOR UPDATE).

        Args:
            variant_id: SupplierVariant UUID

        Returns:
            SupplierVariant instance if found, None otherwise
        """
        result = await self.session.execute(
            select(SupplierVariant)
            .where(SupplierVariant.id == variant_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def reserve(
        self, inventory_id: uuid.UUID, quantity: int
    ) -> Optional[SupplierVariant]:
        """
        Reserve inventory by incrementing reserved_inventory.

        Args:
            inventory_id: SupplierVariant UUID
            quantity: Quantity to reserve

        Returns:
            Updated SupplierVariant instance if found, None otherwise
        """
        result = await self.session.execute(
            update(SupplierVariant)
            .where(SupplierVariant.id == inventory_id)
            .values(reserved_inventory=SupplierVariant.reserved_inventory + quantity)
            .returning(SupplierVariant)
        )
        await self.session.flush()
        return result.scalar_one_or_none()

    async def release(
        self, inventory_id: uuid.UUID, quantity: int
    ) -> Optional[SupplierVariant]:
        """
        Release reservation by decrementing reserved_inventory.

        Args:
            inventory_id: SupplierVariant UUID
            quantity: Quantity to release

        Returns:
            Updated SupplierVariant instance if found, None otherwise
        """
        result = await self.session.execute(
            update(SupplierVariant)
            .where(SupplierVariant.id == inventory_id)
            .values(reserved_inventory=SupplierVariant.reserved_inventory - quantity)
            .returning(SupplierVariant)
        )
        await self.session.flush()
        return result.scalar_one_or_none()

    async def decrement(
        self, inventory_id: uuid.UUID, quantity: int
    ) -> Optional[SupplierVariant]:
        """
        Decrement available inventory quantity.

        Args:
            inventory_id: SupplierVariant UUID
            quantity: Quantity to decrement

        Returns:
            Updated SupplierVariant instance if found, None otherwise
        """
        result = await self.session.execute(
            update(SupplierVariant)
            .where(SupplierVariant.id == inventory_id)
            .values(
                inventory=SupplierVariant.inventory - quantity,
                reserved_inventory=SupplierVariant.reserved_inventory - quantity,
            )
            .returning(SupplierVariant)
        )
        await self.session.flush()
        return result.scalar_one_or_none()

    async def increment(
        self, inventory_id: uuid.UUID, quantity: int
    ) -> Optional[SupplierVariant]:
        """
        Increment available inventory quantity.

        Args:
            inventory_id: SupplierVariant UUID
            quantity: Quantity to increment

        Returns:
            Updated SupplierVariant instance if found, None otherwise
        """
        result = await self.session.execute(
            update(SupplierVariant)
            .where(SupplierVariant.id == inventory_id)
            .values(inventory=SupplierVariant.inventory + quantity)
            .returning(SupplierVariant)
        )
        await self.session.flush()
        return result.scalar_one_or_none()

    async def create(self, data: dict) -> SupplierVariant:
        """
        Create new inventory record.

        Args:
            data: Dictionary containing inventory fields

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
        Update inventory fields.

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
        return await self.get_by_variant_id(id)
