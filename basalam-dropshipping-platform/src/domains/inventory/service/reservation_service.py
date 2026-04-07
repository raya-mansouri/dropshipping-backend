"""
Inventory Reservation Service
============================
Business logic for inventory reservations with deadlock detection and partial reservation support.
"""

import asyncio
import structlog
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from ..models import InventoryReservation, InventoryLog, InventorySource
from ..repository import (
    InventoryRepository,
    InventoryReservationRepository,
    InventoryLogRepository,
)
from src.core.events.publisher import EventPublisher
from src.core.events.base import DomainEvent
from src.core.events.inventory import (
    InventoryReserved,
    InventoryReleased,
    InventoryUpdated,
)

logger = structlog.get_logger(__name__)


@dataclass
class Reservation:
    """Reservation data transfer object"""

    id: uuid4
    variant_id: uuid4
    order_item_id: uuid4
    quantity: int
    status: str
    expires_at: datetime
    released_at: Optional[datetime]
    released_reason: Optional[str]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, model: InventoryReservation) -> "Reservation":
        return cls(
            id=model.id,
            variant_id=model.variant_id,
            order_item_id=model.order_item_id,
            quantity=model.quantity,
            status=model.status,
            expires_at=model.expires_at,
            released_at=model.released_at,
            released_reason=model.released_reason,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


@dataclass
class PartialReservationResult:
    """Result of a partial inventory reservation attempt"""

    success: bool
    reserved_quantity: int
    requested_quantity: int
    available_quantity: int
    message: str
    reservations: List[Reservation]


class DeadlockDetector:
    """Detects and handles database deadlocks with retry logic."""

    MAX_DEADLOCK_RETRIES = 3
    DEADLOCK_ERROR_CODES = {"55P03", "40001"}

    @staticmethod
    def is_deadlock_error(exc: Exception) -> bool:
        """Check if an exception is a deadlock error."""
        error_msg = str(exc).lower()
        return any(code in error_msg for code in DeadlockDetector.DEADLOCK_ERROR_CODES)

    @staticmethod
    async def execute_with_deadlock_retry(
        session: AsyncSession,
        func: callable,
        max_retries: int = MAX_DEADLOCK_RETRIES,
    ) -> any:
        """Execute a function with deadlock retry logic."""
        last_exception = None

        for attempt in range(max_retries):
            try:
                return await func()
            except Exception as exc:
                if DeadlockDetector.is_deadlock_error(exc):
                    last_exception = exc
                    logger.warning(
                        "deadlock_detected_retrying",
                        attempt=attempt + 1,
                        max_retries=max_retries,
                    )
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                raise

        raise last_exception


class ReservationService:
    """
    Service for managing inventory reservations.

    Handles atomic reservation, release, and consumption of inventory
    with proper locking, deadlock detection, and partial reservation support.
    """

    DEFAULT_RESERVATION_MINUTES = 30

    def __init__(
        self,
        session: AsyncSession,
        event_publisher: Optional[EventPublisher] = None,
    ):
        """
        Initialize service with database session.

        Args:
            session: Async SQLAlchemy session for database operations
            event_publisher: Optional EventPublisher for domain events
        """
        self.session = session
        self._event_publisher = event_publisher
        self._inventory_repo = InventoryRepository(session)
        self._reservation_repo = InventoryReservationRepository(session)
        self._log_repo = InventoryLogRepository(session)

    async def _publish_event(self, event: DomainEvent) -> None:
        """Safely publish domain event. Non-blocking - failures are logged but don't raise."""
        if self._event_publisher is None:
            return
        try:
            await self._event_publisher.publish(topic="events", event=event)
        except Exception as e:
            logger.warning("failed_to_publish_event", event_type=event.event_type, error=str(e))

    async def reserve_inventory(
        self,
        variant_id: uuid4,
        order_item_id: uuid4,
        quantity: int,
        expires_in_minutes: Optional[int] = None,
    ) -> Reservation:
        """
        Reserve inventory for an order item.

        Uses SELECT FOR UPDATE for atomic locking and validates
        sufficient inventory is available before reservation.

        Args:
            variant_id: UUID of the supplier variant
            order_item_id: UUID of the order item
            quantity: Quantity to reserve
            expires_in_minutes: Minutes until reservation expires (default: 30)

        Returns:
            Reservation object

        Raises:
            ValueError: If insufficient inventory available
            ValueError: If order item already has an active reservation
        """
        if quantity <= 0:
            raise ValueError("Quantity must be positive")

        existing = await self._reservation_repo.get_by_order(order_item_id)
        active_existing = [r for r in existing if r.status == "reserved"]
        if active_existing:
            raise ValueError(
                f"Order item {order_item_id} already has an active reservation"
            )

        variant = await self._inventory_repo.lock_for_update(variant_id)
        if not variant:
            raise ValueError(f"Variant {variant_id} not found")

        available = variant.inventory - variant.reserved_inventory
        if available < quantity:
            raise ValueError(
                f"Insufficient inventory. Available: {available}, Requested: {quantity}"
            )

        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=expires_in_minutes or self.DEFAULT_RESERVATION_MINUTES
        )

        reservation_data = {
            "variant_id": variant_id,
            "order_item_id": order_item_id,
            "quantity": quantity,
            "status": "reserved",
            "expires_at": expires_at,
        }

        reservation = await self._reservation_repo.create(reservation_data)

        await self._inventory_repo.reserve(variant_id, quantity)

        await self._log_repo.create(
            {
                "variant_id": variant_id,
                "old_inventory": variant.inventory - variant.reserved_inventory,
                "new_inventory": variant.inventory
                - variant.reserved_inventory
                - quantity,
                "change": -quantity,
                "source": InventorySource.ORDER.value,
                "reference_id": order_item_id,
                "reference_type": "order",
                "reason": f"Reserved {quantity} for order item",
                "metadata": {"reservation_id": str(reservation.id)},
            }
        )

        await self._publish_event(
            InventoryReserved(
                variant_id=variant_id,
                order_item_id=order_item_id,
                quantity=quantity,
                expires_at=expires_at,
            )
        )

        return Reservation.from_model(reservation)

    async def reserve_inventory_with_deadlock_retry(
        self,
        variant_id: uuid4,
        order_item_id: uuid4,
        quantity: int,
        expires_in_minutes: Optional[int] = None,
    ) -> Reservation:
        """Reserve inventory with deadlock detection and automatic retry."""

        async def _do_reserve():
            return await self.reserve_inventory(
                variant_id, order_item_id, quantity, expires_in_minutes
            )

        return await DeadlockDetector.execute_with_deadlock_retry(
            self.session, _do_reserve
        )

    async def reserve_inventory_partial(
        self,
        variant_id: uuid4,
        order_item_id: uuid4,
        quantity: int,
        expires_in_minutes: Optional[int] = None,
        allow_partial: bool = False,
    ) -> PartialReservationResult:
        """
        Reserve inventory with support for partial reservations.

        If allow_partial is True and requested quantity exceeds available,
        will reserve whatever is available up to the requested quantity.

        Args:
            variant_id: UUID of the supplier variant
            order_item_id: UUID of the order item
            quantity: Quantity to reserve
            expires_in_minutes: Minutes until reservation expires
            allow_partial: Whether to allow partial reservations

        Returns:
            PartialReservationResult with reservation details
        """
        if quantity <= 0:
            return PartialReservationResult(
                success=False,
                reserved_quantity=0,
                requested_quantity=quantity,
                available_quantity=0,
                message="Quantity must be positive",
                reservations=[],
            )

        existing = await self._reservation_repo.get_by_order(order_item_id)
        active_existing = [r for r in existing if r.status == "reserved"]
        if active_existing:
            return PartialReservationResult(
                success=False,
                reserved_quantity=0,
                requested_quantity=quantity,
                available_quantity=0,
                message=f"Order item {order_item_id} already has an active reservation",
                reservations=[],
            )

        variant = await self._inventory_repo.lock_for_update(variant_id)
        if not variant:
            return PartialReservationResult(
                success=False,
                reserved_quantity=0,
                requested_quantity=quantity,
                available_quantity=0,
                message=f"Variant {variant_id} not found",
                reservations=[],
            )

        available = variant.inventory - variant.reserved_inventory

        if available < quantity:
            if not allow_partial or available == 0:
                return PartialReservationResult(
                    success=False,
                    reserved_quantity=0,
                    requested_quantity=quantity,
                    available_quantity=available,
                    message=f"Insufficient inventory. Available: {available}, Requested: {quantity}",
                    reservations=[],
                )
            quantity = available

        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=expires_in_minutes or self.DEFAULT_RESERVATION_MINUTES
        )

        reservation_data = {
            "variant_id": variant_id,
            "order_item_id": order_item_id,
            "quantity": quantity,
            "status": "reserved",
            "expires_at": expires_at,
        }

        reservation = await self._reservation_repo.create(reservation_data)
        await self._inventory_repo.reserve(variant_id, quantity)

        await self._log_repo.create(
            {
                "variant_id": variant_id,
                "old_inventory": variant.inventory - variant.reserved_inventory,
                "new_inventory": variant.inventory
                - variant.reserved_inventory
                - quantity,
                "change": -quantity,
                "source": InventorySource.ORDER.value,
                "reference_id": order_item_id,
                "reference_type": "order",
                "reason": f"Reserved {quantity} for order item",
                "metadata": {"reservation_id": str(reservation.id)},
            }
        )

        return PartialReservationResult(
            success=True,
            reserved_quantity=quantity,
            requested_quantity=quantity,
            available_quantity=available,
            message=f"Reserved {quantity} units (requested: {quantity})",
            reservations=[Reservation.from_model(reservation)],
        )

    async def release_inventory(
        self,
        order_item_id: uuid.UUID,
        reason: str = "cancelled",
    ) -> bool:
        """
        Release inventory reservation for an order item.

        Args:
            order_item_id: UUID of the order item
            reason: Reason for release (default: "cancelled")

        Returns:
            True if released successfully
        """
        reservations = await self._reservation_repo.get_by_order(order_item_id)
        active_reservations = [r for r in reservations if r.status == "reserved"]

        if not active_reservations:
            return False

        for reservation in active_reservations:
            variant = await self._inventory_repo.lock_for_update(reservation.variant_id)
            if not variant:
                continue

            old_reserved = variant.reserved_inventory
            await self._inventory_repo.release(
                reservation.variant_id, reservation.quantity
            )

            await self.session.execute(
                update(InventoryReservation)
                .where(InventoryReservation.id == reservation.id)
                .values(
                    status="released",
                    released_at=datetime.now(timezone.utc),
                    released_reason=reason,
                )
            )
            await self.session.flush()

            await self._log_repo.create(
                {
                    "variant_id": reservation.variant_id,
                    "old_inventory": variant.inventory - old_reserved,
                    "new_inventory": variant.inventory
                    - (old_reserved - reservation.quantity),
                    "change": reservation.quantity,
                    "source": InventorySource.CORRECTION.value,
                    "reference_id": order_item_id,
                    "reference_type": "order",
                    "reason": f"Released reservation: {reason}",
                    "metadata": {
                        "reservation_id": str(reservation.id),
                        "reason": reason,
                    },
                }
            )

            await self._publish_event(
                InventoryReleased(
                    variant_id=reservation.variant_id,
                    order_item_id=order_item_id,
                    quantity=reservation.quantity,
                    reason=reason,
                )
            )

        return True

    async def consume_inventory(self, order_item_id: uuid.UUID) -> bool:
        """
        Consume inventory reservation for a paid order.

        Finalizes the reservation and decrements actual inventory.

        Args:
            order_item_id: UUID of the order item

        Returns:
            True if consumed successfully
        """
        reservations = await self._reservation_repo.get_by_order(order_item_id)
        active_reservations = [r for r in reservations if r.status == "reserved"]

        if not active_reservations:
            return False

        for reservation in active_reservations:
            variant = await self._inventory_repo.lock_for_update(reservation.variant_id)
            if not variant:
                continue

            old_inventory = variant.inventory
            await self._inventory_repo.decrement(
                reservation.variant_id, reservation.quantity
            )

            await self.session.execute(
                update(InventoryReservation)
                .where(InventoryReservation.id == reservation.id)
                .values(status="consumed")
            )
            await self.session.flush()

            await self._log_repo.create(
                {
                    "variant_id": reservation.variant_id,
                    "old_inventory": old_inventory,
                    "new_inventory": old_inventory - reservation.quantity,
                    "change": -reservation.quantity,
                    "source": InventorySource.ORDER.value,
                    "reference_id": order_item_id,
                    "reference_type": "order",
                    "reason": "Inventory consumed for order",
                    "metadata": {"reservation_id": str(reservation.id)},
                }
            )

            await self._publish_event(
                InventoryUpdated(
                    variant_id=reservation.variant_id,
                    old_quantity=old_inventory,
                    new_quantity=old_inventory - reservation.quantity,
                    source="order_consumed",
                )
            )

        return True

    async def get_reservation(self, order_item_id: uuid.UUID) -> Optional[Reservation]:
        """
        Get active reservation for an order item.

        Args:
            order_item_id: UUID of the order item

        Returns:
            Reservation object if found, None otherwise
        """
        reservations = await self._reservation_repo.get_by_order(order_item_id)
        active = next(
            (r for r in reservations if r.status == "reserved"),
            None,
        )
        if active:
            return Reservation.from_model(active)
        return None

    async def get_expired_reservations(self) -> List[Reservation]:
        """
        Get all expired reservations.

        Returns:
            List of expired Reservation objects
        """
        expired = await self._reservation_repo.get_expired()
        return [Reservation.from_model(r) for r in expired]
