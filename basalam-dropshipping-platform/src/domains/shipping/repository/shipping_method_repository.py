"""
Shipping Method Repository
==========================
Database access for ShippingMethod entities (defined in shops/models.py).
"""
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.shops.models import ShippingMethod


class ShippingMethodRepository:
    """Repository for shipping method persistence."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, method_id: UUID) -> Optional[ShippingMethod]:
        result = await self.session.execute(
            select(ShippingMethod).where(ShippingMethod.id == method_id)
        )
        return result.scalar_one_or_none()

    async def get_by_platform(self, platform_id: UUID) -> List[ShippingMethod]:
        result = await self.session.execute(
            select(ShippingMethod).where(
                ShippingMethod.platform_id == platform_id,
                ShippingMethod.active.is_(True),
            )
        )
        return list(result.scalars().all())

    async def get_all_active(self) -> List[ShippingMethod]:
        result = await self.session.execute(
            select(ShippingMethod).where(ShippingMethod.active.is_(True))
        )
        return list(result.scalars().all())

    async def upsert_from_sync(
        self,
        platform_id: UUID,
        external_id: str,
        name: str,
        shipping_type: str,
    ) -> ShippingMethod:
        """Create or update a shipping method from platform sync."""
        existing = await self.session.execute(
            select(ShippingMethod).where(
                ShippingMethod.platform_id == platform_id,
                ShippingMethod.external_shipping_id == external_id,
            )
        )
        method = existing.scalar_one_or_none()

        if method:
            method.name = name
            method.shipping_type = shipping_type
            method.active = True
        else:
            method = ShippingMethod(
                platform_id=platform_id,
                external_shipping_id=external_id,
                name=name,
                shipping_type=shipping_type,
                active=True,
            )
            self.session.add(method)

        await self.session.flush()
        await self.session.refresh(method)
        return method
