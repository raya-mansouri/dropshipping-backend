"""
Fraud Detection Repository
==========================
Database access for fraud signal entries.
"""
from typing import List, Optional
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import FraudSignal


class FraudSignalRepository:
    """Repository for fraud signal persistence."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, signal_id: UUID) -> Optional[FraudSignal]:
        """Get a fraud signal by ID."""
        result = await self.session.execute(
            select(FraudSignal).where(FraudSignal.id == signal_id)
        )
        return result.scalar_one_or_none()

    async def get_by_entity(
        self, entity_type: str, entity_id: UUID, limit: int = 100
    ) -> List[FraudSignal]:
        """Get fraud signals for a specific entity."""
        stmt = (
            select(FraudSignal)
            .where(
                FraudSignal.entity_type == entity_type,
                FraudSignal.entity_id == entity_id,
            )
            .order_by(FraudSignal.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_status(
        self, status: str, limit: int = 100
    ) -> List[FraudSignal]:
        """Get fraud signals by status."""
        stmt = (
            select(FraudSignal)
            .where(FraudSignal.status == status)
            .order_by(FraudSignal.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_severity(
        self, severity: str, limit: int = 100
    ) -> List[FraudSignal]:
        """Get fraud signals by severity level."""
        stmt = (
            select(FraudSignal)
            .where(FraudSignal.severity == severity)
            .order_by(FraudSignal.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, data: dict) -> FraudSignal:
        """Create a new fraud signal."""
        signal = FraudSignal(**data)
        self.session.add(signal)
        await self.session.flush()
        await self.session.refresh(signal)
        return signal

    async def update_status(
        self,
        signal_id: UUID,
        status: str,
    ) -> Optional[FraudSignal]:
        """Update the status of a fraud signal."""
        signal = await self.get_by_id(signal_id)
        if not signal:
            return None
        signal.status = status
        if status in ("resolved", "false_positive"):
            signal.resolved_at = datetime.now(timezone.utc)
        await self.session.flush()
        await self.session.refresh(signal)
        return signal
