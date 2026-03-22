"""
Inventory Log Repository
========================
Repository for InventoryLog model operations
"""

from typing import Optional, List
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import InventoryLog


class InventoryLogRepository:
    """
    Repository for managing InventoryLog entities.

    Handles database operations for inventory change audit logs
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize repository with database session.

        Args:
            session: Async SQLAlchemy session
        """
        self.session = session

    async def get_by_variant(self, variant_id: uuid.UUID) -> List[InventoryLog]:
        """
        Get all logs for a variant.

        Args:
            variant_id: SupplierVariant UUID

        Returns:
            List of InventoryLog instances for the variant
        """
        result = await self.session.execute(
            select(InventoryLog)
            .where(InventoryLog.variant_id == variant_id)
            .order_by(InventoryLog.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_order(self, order_id: uuid.UUID) -> List[InventoryLog]:
        """
        Get all logs for an order.

        Args:
            order_id: Order UUID

        Returns:
            List of InventoryLog instances for the order
        """
        result = await self.session.execute(
            select(InventoryLog)
            .where(
                InventoryLog.reference_id == order_id,
                InventoryLog.reference_type == "order",
            )
            .order_by(InventoryLog.created_at.desc())
        )
        return list(result.scalars().all())

    async def create(self, data: dict) -> InventoryLog:
        """
        Create a new log entry.

        Args:
            data: Dictionary containing log fields

        Returns:
            Newly created InventoryLog instance
        """
        log = InventoryLog(**data)
        self.session.add(log)
        await self.session.flush()
        await self.session.refresh(log)
        return log
