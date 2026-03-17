"""
Unit Tests for Inventory Reservation
=====================================
Tests for inventory reservation logic
"""

import uuid
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from src.domains.inventory.service.reservation_service import (
    ReservationService,
    Reservation,
)
from src.domains.inventory.models import InventoryReservation


class TestInventoryReservation:
    """Test suite for inventory reservation functionality."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        return session

    @pytest.fixture
    def reservation_service(self, mock_session):
        """Create a ReservationService with mock session."""
        return ReservationService(mock_session)

    @pytest.fixture
    def sample_variant_id(self):
        """Create a sample variant UUID."""
        return uuid.uuid4()

    @pytest.fixture
    def sample_order_item_id(self):
        """Create a sample order item UUID."""
        return uuid.uuid4()

    @pytest.fixture
    def mock_variant(self, sample_variant_id):
        """Create a mock inventory variant."""
        variant = MagicMock()
        variant.id = sample_variant_id
        variant.inventory = 100
        variant.reserved_inventory = 0
        return variant

    @pytest.fixture
    def mock_reservation(self, sample_variant_id, sample_order_item_id):
        """Create a mock reservation."""
        reservation = MagicMock(spec=InventoryReservation)
        reservation.id = uuid.uuid4()
        reservation.variant_id = sample_variant_id
        reservation.order_item_id = sample_order_item_id
        reservation.quantity = 5
        reservation.status = "reserved"
        reservation.expires_at = datetime.utcnow() + timedelta(minutes=30)
        reservation.released_at = None
        reservation.released_reason = None
        reservation.created_at = datetime.utcnow()
        reservation.updated_at = datetime.utcnow()
        return reservation

    @pytest.mark.asyncio
    async def test_reserve_inventory_success(
        self, reservation_service, mock_session, sample_variant_id, sample_order_item_id
    ):
        """Test successful inventory reservation."""
        mock_variant = MagicMock()
        mock_variant.id = sample_variant_id
        mock_variant.inventory = 100
        mock_variant.reserved_inventory = 0

        with patch.object(
            reservation_service._inventory_repo,
            "lock_for_update",
            new_callable=AsyncMock,
        ) as mock_lock:
            with patch.object(
                reservation_service._reservation_repo,
                "get_by_order",
                new_callable=AsyncMock,
                return_value=[],
            ):
                with patch.object(
                    reservation_service._reservation_repo,
                    "create",
                    new_callable=AsyncMock,
                ) as mock_create:
                    with patch.object(
                        reservation_service._inventory_repo,
                        "reserve",
                        new_callable=AsyncMock,
                    ):
                        with patch.object(
                            reservation_service._log_repo,
                            "create",
                            new_callable=AsyncMock,
                        ):
                            mock_lock.return_value = mock_variant
                            mock_reservation = MagicMock(spec=InventoryReservation)
                            mock_reservation.id = uuid.uuid4()
                            mock_reservation.variant_id = sample_variant_id
                            mock_reservation.order_item_id = sample_order_item_id
                            mock_reservation.quantity = 5
                            mock_reservation.status = "reserved"
                            mock_reservation.expires_at = datetime.utcnow() + timedelta(
                                minutes=30
                            )
                            mock_reservation.released_at = None
                            mock_reservation.released_reason = None
                            mock_reservation.created_at = datetime.utcnow()
                            mock_reservation.updated_at = datetime.utcnow()
                            mock_create.return_value = mock_reservation

                            result = await reservation_service.reserve_inventory(
                                variant_id=sample_variant_id,
                                order_item_id=sample_order_item_id,
                                quantity=5,
                            )

                            assert result is not None
                            assert result.variant_id == sample_variant_id
                            assert result.quantity == 5
                            assert result.status == "reserved"

    @pytest.mark.asyncio
    async def test_reserve_inventory_insufficient_inventory(
        self, reservation_service, mock_session, sample_variant_id, sample_order_item_id
    ):
        """Test reservation fails with insufficient inventory."""
        mock_variant = MagicMock()
        mock_variant.id = sample_variant_id
        mock_variant.inventory = 10
        mock_variant.reserved_inventory = 0

        with patch.object(
            reservation_service._inventory_repo,
            "lock_for_update",
            new_callable=AsyncMock,
        ) as mock_lock:
            with patch.object(
                reservation_service._reservation_repo,
                "get_by_order",
                new_callable=AsyncMock,
                return_value=[],
            ):
                mock_lock.return_value = mock_variant

                with pytest.raises(ValueError) as exc_info:
                    await reservation_service.reserve_inventory(
                        variant_id=sample_variant_id,
                        order_item_id=sample_order_item_id,
                        quantity=50,
                    )

                assert "Insufficient inventory" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_reserve_inventory_negative_quantity(
        self, reservation_service, sample_variant_id, sample_order_item_id
    ):
        """Test reservation fails with negative quantity."""
        with pytest.raises(ValueError) as exc_info:
            await reservation_service.reserve_inventory(
                variant_id=sample_variant_id,
                order_item_id=sample_order_item_id,
                quantity=-5,
            )

        assert "Quantity must be positive" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_reserve_inventory_duplicate_order(
        self, reservation_service, mock_session, sample_variant_id, sample_order_item_id
    ):
        """Test reservation fails when order already has active reservation."""
        existing_reservation = MagicMock(spec=InventoryReservation)
        existing_reservation.status = "reserved"

        with patch.object(
            reservation_service._reservation_repo,
            "get_by_order",
            new_callable=AsyncMock,
            return_value=[existing_reservation],
        ):
            with pytest.raises(ValueError) as exc_info:
                await reservation_service.reserve_inventory(
                    variant_id=sample_variant_id,
                    order_item_id=sample_order_item_id,
                    quantity=5,
                )

            assert "already has an active reservation" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_release_inventory_success(
        self, reservation_service, mock_session, mock_reservation
    ):
        """Test successful inventory release."""
        with patch.object(
            reservation_service._reservation_repo,
            "get_by_order",
            new_callable=AsyncMock,
            return_value=[mock_reservation],
        ):
            with patch.object(
                reservation_service._inventory_repo,
                "lock_for_update",
                new_callable=AsyncMock,
            ) as mock_lock:
                with patch.object(
                    reservation_service._inventory_repo,
                    "release",
                    new_callable=AsyncMock,
                ):
                    with patch.object(
                        reservation_service._log_repo,
                        "create",
                        new_callable=AsyncMock,
                    ):
                        mock_lock.return_value = MagicMock(
                            inventory=100, reserved_inventory=5
                        )

                        result = await reservation_service.release_inventory(
                            order_item_id=mock_reservation.order_item_id,
                            reason="cancelled",
                        )

                        assert result is True

    @pytest.mark.asyncio
    async def test_release_inventory_no_reservation(
        self, reservation_service, mock_session, sample_order_item_id
    ):
        """Test release fails when no active reservation exists."""
        with patch.object(
            reservation_service._reservation_repo,
            "get_by_order",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await reservation_service.release_inventory(
                order_item_id=sample_order_item_id,
                reason="cancelled",
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_concurrent_reservation_race_condition(
        self, reservation_service, mock_session, sample_variant_id
    ):
        """Test concurrent reservations handle race condition correctly."""
        order_item_1 = uuid.uuid4()
        order_item_2 = uuid.uuid4()

        mock_variant = MagicMock()
        mock_variant.id = sample_variant_id
        mock_variant.inventory = 10
        mock_variant.reserved_inventory = 0

        async def mock_lock(variant_id):
            mock_variant.reserved_inventory = 10
            return mock_variant

        with patch.object(
            reservation_service._inventory_repo,
            "lock_for_update",
            new_callable=AsyncMock,
            side_effect=mock_lock,
        ):
            with patch.object(
                reservation_service._reservation_repo,
                "get_by_order",
                new_callable=AsyncMock,
                return_value=[],
            ):
                with patch.object(
                    reservation_service._reservation_repo,
                    "create",
                    new_callable=AsyncMock,
                ) as mock_create:
                    with patch.object(
                        reservation_service._inventory_repo,
                        "reserve",
                        new_callable=AsyncMock,
                    ):
                        with patch.object(
                            reservation_service._log_repo,
                            "create",
                            new_callable=AsyncMock,
                        ):
                            mock_reservation = MagicMock(spec=InventoryReservation)
                            mock_reservation.id = uuid.uuid4()
                            mock_reservation.variant_id = sample_variant_id
                            mock_reservation.quantity = 10
                            mock_reservation.status = "reserved"
                            mock_reservation.expires_at = datetime.utcnow() + timedelta(
                                minutes=30
                            )
                            mock_create.return_value = mock_reservation

                            result = await reservation_service.reserve_inventory(
                                variant_id=sample_variant_id,
                                order_item_id=order_item_1,
                                quantity=10,
                            )

                            assert result.quantity == 10
                            assert result.status == "reserved"
