"""
Shipment Repository
===================
Repository for Shipment model operations
"""

from typing import Optional, List
import uuid
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Shipment


class ShipmentRepository:
    """
    Repository for managing Shipment entities.

    Handles database operations for shipment records
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, id: uuid.UUID) -> Optional[Shipment]:
        result = await self.session.execute(select(Shipment).where(Shipment.id == id))
        return result.scalar_one_or_none()

    async def get_by_order(self, order_id: uuid.UUID) -> List[Shipment]:
        result = await self.session.execute(
            select(Shipment).where(Shipment.order_id == order_id)
        )
        return list(result.scalars().all())

    async def get_by_tracking(self, tracking_number: str) -> Optional[Shipment]:
        result = await self.session.execute(
            select(Shipment).where(Shipment.tracking_code == tracking_number)
        )
        return result.scalar_one_or_none()

    async def get_pending_delivery(self) -> List[Shipment]:
        result = await self.session.execute(
            select(Shipment)
            .where(Shipment.status.in_(["shipped", "in_transit"]))
            .order_by(Shipment.estimated_delivery.asc())
        )
        return list(result.scalars().all())

    async def create(self, data: dict) -> Shipment:
        shipment = Shipment(**data)
        self.session.add(shipment)
        await self.session.flush()
        await self.session.refresh(shipment)
        return shipment

    async def update(self, id: uuid.UUID, data: dict) -> Optional[Shipment]:
        await self.session.execute(
            update(Shipment).where(Shipment.id == id).values(**data)
        )
        await self.session.flush()
        return await self.get_by_id(id)

    async def update_status(self, id: uuid.UUID, status: str) -> Optional[Shipment]:
        return await self.update(id, {"status": status})
