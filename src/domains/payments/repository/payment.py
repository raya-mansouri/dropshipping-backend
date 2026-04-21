"""
Payment Repository
==================
Repository for Payment model operations
"""

from typing import Optional, List
import uuid
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Payment, PaymentStatus


class PaymentRepository:
    """
    Repository for managing Payment entities.

    Handles database operations for payment records
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, id: uuid.UUID) -> Optional[Payment]:
        result = await self.session.execute(select(Payment).where(Payment.id == id))
        return result.scalar_one_or_none()

    async def get_by_order(self, order_id: uuid.UUID) -> List[Payment]:
        result = await self.session.execute(
            select(Payment)
            .where(Payment.order_id == order_id)
            .order_by(Payment.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_external_id(self, external_id: str) -> Optional[Payment]:
        result = await self.session.execute(
            select(Payment).where(Payment.gateway_transaction_id == external_id)
        )
        return result.scalar_one_or_none()

    async def get_by_status(self, status: PaymentStatus) -> List[Payment]:
        result = await self.session.execute(
            select(Payment)
            .where(Payment.status == status.value)
            .order_by(Payment.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_escrow_pending(self) -> List[Payment]:
        result = await self.session.execute(
            select(Payment)
            .where(Payment.status == PaymentStatus.SELLER_PAID.value)
            .order_by(Payment.paid_at.asc())
        )
        return list(result.scalars().all())

    async def create(self, data: dict) -> Payment:
        payment = Payment(**data)
        self.session.add(payment)
        await self.session.flush()
        await self.session.refresh(payment)
        return payment

    async def update(self, id: uuid.UUID, data: dict) -> Optional[Payment]:
        await self.session.execute(
            update(Payment).where(Payment.id == id).values(**data)
        )
        await self.session.flush()
        return await self.get_by_id(id)

    async def update_status(
        self, id: uuid.UUID, status: PaymentStatus
    ) -> Optional[Payment]:
        return await self.update(id, {"status": status.value})
