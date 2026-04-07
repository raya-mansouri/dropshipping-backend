"""
Fraud Detection Service
=======================
Business logic for fraud signal detection and management.
"""
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from .models import FraudSignal
from .repository import FraudSignalRepository

logger = structlog.get_logger(__name__)


class FraudDetectionService:
    """Service for managing fraud signals."""

    def __init__(self, session: AsyncSession):
        self.repo = FraudSignalRepository(session)

    async def record_signal(
        self,
        entity_type: str,
        entity_id: UUID,
        signal_type: str,
        severity: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> FraudSignal:
        """Record a new fraud signal."""
        signal = await self.repo.create({
            "entity_type": entity_type,
            "entity_id": entity_id,
            "signal_type": signal_type,
            "severity": severity,
            "data": data or {},
            "status": "new",
            "created_at": datetime.now(timezone.utc),
        })
        logger.info(
            "fraud_signal_recorded",
            entity_type=entity_type,
            entity_id=str(entity_id),
            signal_type=signal_type,
            severity=severity,
            signal_id=str(signal.id),
        )
        return signal

    async def resolve_signal(
        self,
        signal_id: UUID,
        resolution: str = "resolved",
    ) -> Optional[FraudSignal]:
        """Resolve a fraud signal."""
        signal = await self.repo.update_status(signal_id, resolution)
        if signal:
            logger.info(
                "fraud_signal_resolved",
                signal_id=str(signal_id),
                resolution=resolution,
            )
        return signal

    async def get_entity_signals(
        self, entity_type: str, entity_id: UUID, limit: int = 50
    ) -> List[FraudSignal]:
        """Get fraud signals for a specific entity."""
        return await self.repo.get_by_entity(entity_type, entity_id, limit=limit)

    async def get_pending_signals(
        self, severity: Optional[str] = None, limit: int = 50
    ) -> List[FraudSignal]:
        """Get pending (new/investigating) fraud signals."""
        if severity:
            return await self.repo.get_by_severity(severity, limit=limit)
        return await self.repo.get_by_status("new", limit=limit)
