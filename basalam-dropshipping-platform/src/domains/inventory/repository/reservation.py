"""
Inventory Reservation Repository
================================
Repository for InventoryReservation model operations
"""

from typing import Optional, List
import uuid
from datetime import datetime, timezone
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import InventoryReservation


class InventoryReservationRepository:
    """
    Repository for managing InventoryReservation entities.

    Handles database operations for inventory reservations
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize repository with database session.

        Args:
            session: Async SQLAlchemy session
        """
        self.session = session

    async def get_by_id(self, id: uuid.UUID) -> Optional[InventoryReservation]:
        """
        Get reservation by UUID.

        Args:
            id: Reservation UUID

        Returns:
            InventoryReservation instance if found, None otherwise
        """
        result = await self.session.execute(
            select(InventoryReservation).where(InventoryReservation.id == id)
        )
        return result.scalar_one_or_none()

    async def get_by_order(self, order_id: uuid.UUID) -> List[InventoryReservation]:
        """
        Get all reservations for an order.

        Args:
            order_id: Order UUID

        Returns:
            List of InventoryReservation instances for the order
        """
        result = await self.session.execute(
            select(InventoryReservation)
            .where(InventoryReservation.order_item_id == order_id)
            .order_by(InventoryReservation.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_variant(self, variant_id: uuid.UUID) -> List[InventoryReservation]:
        """
        Get active reservations for a variant.

        Args:
            variant_id: SupplierVariant UUID

        Returns:
            List of active InventoryReservation instances for the variant
        """
        result = await self.session.execute(
            select(InventoryReservation)
            .where(
                InventoryReservation.variant_id == variant_id,
                InventoryReservation.status == "reserved",
            )
            .order_by(InventoryReservation.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_expired(self) -> List[InventoryReservation]:
        """
        Get expired reservations.

        Returns:
            List of expired InventoryReservation instances
        """
        result = await self.session.execute(
            select(InventoryReservation)
            .where(
                InventoryReservation.status == "reserved",
                InventoryReservation.expires_at < datetime.now(timezone.utc),
            )
            .order_by(InventoryReservation.expires_at.asc())
        )
        return list(result.scalars().all())

    async def create(self, data: dict) -> InventoryReservation:
        """
        Create a new reservation.

        Args:
            data: Dictionary containing reservation fields

        Returns:
            Newly created InventoryReservation instance
        """
        reservation = InventoryReservation(**data)
        self.session.add(reservation)
        await self.session.flush()
        await self.session.refresh(reservation)
        return reservation

    async def expire(self, id: uuid.UUID) -> Optional[InventoryReservation]:
        """
        Mark reservation as expired.

        Args:
            id: Reservation UUID

        Returns:
            Updated InventoryReservation instance if found, None otherwise
        """
        await self.session.execute(
            update(InventoryReservation)
            .where(InventoryReservation.id == id)
            .values(
                status="expired",
                released_at=datetime.now(timezone.utc),
                released_reason="payment_timeout",
            )
        )
        await self.session.flush()
        return await self.get_by_id(id)
