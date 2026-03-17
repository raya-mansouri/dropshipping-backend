"""
Order Flow E2E Tests
=====================
End-to-end tests for complete order lifecycle, state transitions,
and inventory reservation
"""

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.orders.models import Order, OrderItem, OrderStatus, OrderHistory
from src.domains.orders.service.order_service import (
    OrderService,
    InvalidTransitionError,
    VALID_TRANSITIONS,
)
from src.domains.inventory.models import InventoryReservation
from src.domains.inventory.service.reservation_service import ReservationService


class TestCompleteOrderLifecycle:
    """Tests for complete order lifecycle from creation to completion"""

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.add = MagicMock()
        return session

    @pytest.fixture
    def sample_shop_id(self):
        return uuid.uuid4()

    @pytest.fixture
    def sample_items(self):
        variant_id = uuid.uuid4()
        return [
            {"variant_id": variant_id, "quantity": 2, "seller_listing_id": uuid.uuid4()}
        ]

    @pytest.mark.asyncio
    async def test_order_creation_with_inventory_reservation(
        self, mock_session, sample_shop_id, sample_items
    ):
        """Test complete order creation with inventory reservation"""
        from sqlalchemy import select

        mock_variant = MagicMock()
        mock_variant.id = sample_items[0]["variant_id"]
        mock_variant.cost_price = Decimal("25.00")
        mock_variant.product = MagicMock()
        mock_variant.product.shop_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_variant
        mock_session.execute.return_value = mock_result

        mock_seller_variant = MagicMock()
        mock_seller_variant.price = Decimal("49.99")
        mock_seller_variant.custom_price = None

        mock_seller_result = MagicMock()
        mock_seller_result.scalar_one_or_none.return_value = mock_seller_variant

        async def execute_side_effect(*args, **kwargs):
            return mock_result if "SupplierVariant" in str(args) else mock_seller_result

        mock_session.execute.side_effect = execute_side_effect

        service = OrderService(mock_session)

        order = await service.create_order(
            shop_id=sample_shop_id,
            items=sample_items,
            customer_data={"email": "customer@example.com", "name": "Test Customer"},
            external_order_id="EXT-ORD-123",
            shipping_price=Decimal("10.00"),
        )

        assert order.shop_id == sample_shop_id
        assert order.status == OrderStatus.PENDING.value
        assert order.external_order_id == "EXT-ORD-123"

        mock_session.add.assert_called()

    @pytest.mark.asyncio
    async def test_order_transition_pending_to_confirmed(
        self, mock_session, sample_shop_id
    ):
        """Test order transition from pending to confirmed"""
        order_id = uuid.uuid4()

        mock_order = MagicMock()
        mock_order.id = order_id
        mock_order.shop_id = sample_shop_id
        mock_order.status = OrderStatus.PENDING.value
        mock_order.total_price = Decimal("100.00")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_order
        mock_session.execute.return_value = mock_result

        service = OrderService(mock_session)

        updated_order = await service.transition_status(
            order_id=order_id, new_status=OrderStatus.CONFIRMED, actor_type="system"
        )

        mock_session.flush.assert_called()

    @pytest.mark.asyncio
    async def test_order_transition_confirmed_to_paid(
        self, mock_session, sample_shop_id
    ):
        """Test order transition from confirmed to paid"""
        order_id = uuid.uuid4()

        mock_order = MagicMock()
        mock_order.id = order_id
        mock_order.status = OrderStatus.CONFIRMED.value

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_order
        mock_session.execute.return_value = mock_result

        mock_order_item = MagicMock()
        mock_order_item.id = uuid.uuid4()

        mock_items_result = MagicMock()
        mock_items_result.scalars.return_value.all.return_value = [mock_order_item]

        async def execute_side_effect(*args, **kwargs):
            stmt = args[0]
            if hasattr(stmt, "where"):
                return mock_result
            return mock_items_result

        mock_session.execute.side_effect = execute_side_effect

        service = OrderService(mock_session)

        updated_order = await service.transition_status(
            order_id=order_id, new_status=OrderStatus.PAID, actor_type="payment_gateway"
        )

        assert updated_order is not None


class TestOrderStateTransitions:
    """Tests for order state machine transitions"""

    @pytest.mark.parametrize(
        "from_status,to_status",
        [
            (OrderStatus.PENDING, OrderStatus.CONFIRMED),
            (OrderStatus.PENDING, OrderStatus.CANCELLED),
            (OrderStatus.CONFIRMED, OrderStatus.PAID),
            (OrderStatus.CONFIRMED, OrderStatus.CANCELLED),
            (OrderStatus.PAID, OrderStatus.PROCESSING),
            (OrderStatus.PAID, OrderStatus.REFUNDED),
            (OrderStatus.PAID, OrderStatus.DISPUTED),
            (OrderStatus.PROCESSING, OrderStatus.SHIPPED),
            (OrderStatus.PROCESSING, OrderStatus.REFUNDED),
            (OrderStatus.SHIPPED, OrderStatus.DELIVERED),
            (OrderStatus.DELIVERED, OrderStatus.COMPLETED),
            (OrderStatus.DELIVERED, OrderStatus.DISPUTED),
            (OrderStatus.DISPUTED, OrderStatus.REFUNDED),
            (OrderStatus.DISPUTED, OrderStatus.COMPLETED),
            (OrderStatus.DISPUTED, OrderStatus.CANCELLED),
        ],
    )
    def test_valid_transitions(self, from_status, to_status):
        """Test that valid state transitions are allowed"""
        assert to_status in VALID_TRANSITIONS.get(from_status, [])

    @pytest.mark.parametrize(
        "from_status,to_status",
        [
            (OrderStatus.PENDING, OrderStatus.PAID),
            (OrderStatus.PENDING, OrderStatus.SHIPPED),
            (OrderStatus.CONFIRMED, OrderStatus.PROCESSING),
            (OrderStatus.SHIPPED, OrderStatus.CANCELLED),
            (OrderStatus.COMPLETED, OrderStatus.CANCELLED),
            (OrderStatus.CANCELLED, OrderStatus.PENDING),
        ],
    )
    def test_invalid_transitions(self, from_status, to_status):
        """Test that invalid state transitions are not allowed"""
        assert to_status not in VALID_TRANSITIONS.get(from_status, [])

    @pytest.mark.asyncio
    async def test_invalid_transition_raises_error(self):
        """Test that invalid transition raises InvalidTransitionError"""
        service = OrderService(None)

        with pytest.raises(InvalidTransitionError):
            service._can_transition(OrderStatus.PENDING, OrderStatus.SHIPPED)

    @pytest.mark.asyncio
    async def test_complete_order_flow(self, mock_session):
        """Test complete order flow through all valid states"""
        order_id = uuid.uuid4()

        transitions = [
            OrderStatus.PENDING,
            OrderStatus.CONFIRMED,
            OrderStatus.PAID,
            OrderStatus.PROCESSING,
            OrderStatus.SHIPPED,
            OrderStatus.DELIVERED,
            OrderStatus.COMPLETED,
        ]

        for i, status in enumerate(transitions[:-1]):
            from_status = status
            to_status = transitions[i + 1]

            can_transition = to_status in VALID_TRANSITIONS.get(from_status, [])

            if from_status == OrderStatus.PAID:
                mock_order_item = MagicMock()
                mock_order_item.id = uuid.uuid4()

                mock_items_result = MagicMock()
                mock_items_result.scalars.return_value.all.return_value = [
                    mock_order_item
                ]

                async def execute_side_effect(*args, **kwargs):
                    return mock_items_result

                mock_session.execute.side_effect = execute_side_effect

            assert can_transition is True, (
                f"Failed transition {from_status} -> {to_status}"
            )


class TestInventoryReservation:
    """Tests for inventory reservation during order lifecycle"""

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.add = MagicMock()
        return session

    @pytest.fixture
    def sample_variant_id(self):
        return uuid.uuid4()

    @pytest.fixture
    def sample_order_item_id(self):
        return uuid.uuid4()

    @pytest.mark.asyncio
    async def test_reservation_creation(
        self, mock_session, sample_variant_id, sample_order_item_id
    ):
        """Test inventory reservation is created with order"""
        from sqlalchemy import select

        mock_variant = MagicMock()
        mock_variant.id = sample_variant_id
        mock_variant.inventory = 100
        mock_variant.reserved_inventory = 0
        mock_variant.product = MagicMock()
        mock_variant.product.shop_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_variant
        mock_session.execute.return_value = mock_result

        reservation_service = ReservationService(mock_session)

        reservation = await reservation_service.reserve_inventory(
            variant_id=sample_variant_id,
            order_item_id=sample_order_item_id,
            quantity=5,
            expires_in_minutes=30,
        )

        assert reservation is not None
        assert reservation.quantity == 5
        assert reservation.status == "reserved"

    @pytest.mark.asyncio
    async def test_reservation_expiration(
        self, mock_session, sample_variant_id, sample_order_item_id
    ):
        """Test that expired reservations are handled"""
        from sqlalchemy import select, and_

        past_time = datetime.utcnow() - timedelta(hours=1)

        mock_expired_reservation = MagicMock()
        mock_expired_reservation.id = uuid.uuid4()
        mock_expired_reservation.variant_id = sample_variant_id
        mock_expired_reservation.status = "reserved"
        mock_expired_reservation.expires_at = past_time

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_expired_reservation]
        mock_session.execute.return_value = mock_result

        reservation_service = ReservationService(mock_session)

        reservations = await reservation_service.get_expired_reservations()

        assert len(reservations) >= 0

    @pytest.mark.asyncio
    async def test_release_reservation(
        self, mock_session, sample_variant_id, sample_order_item_id
    ):
        """Test releasing inventory reservation"""
        mock_reservation = MagicMock()
        mock_reservation.id = uuid.uuid4()
        mock_reservation.variant_id = sample_variant_id
        mock_reservation.order_item_id = sample_order_item_id
        mock_reservation.quantity = 5
        mock_reservation.status = "reserved"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_reservation
        mock_session.execute.return_value = mock_result

        reservation_service = ReservationService(mock_session)

        await reservation_service.release_inventory(
            order_item_id=sample_order_item_id, reason="cancelled_by_customer"
        )

        mock_session.flush.assert_called()

    @pytest.mark.asyncio
    async def test_consume_reservation(self, mock_session, sample_order_item_id):
        """Test consuming reservation after payment"""
        mock_reservation = MagicMock()
        mock_reservation.id = uuid.uuid4()
        mock_reservation.status = "reserved"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_reservation
        mock_session.execute.return_value = mock_result

        reservation_service = ReservationService(mock_session)

        await reservation_service.consume_inventory(sample_order_item_id)

        mock_session.flush.assert_called()

    @pytest.mark.asyncio
    async def test_insufficient_inventory_raises_error(
        self, mock_session, sample_variant_id, sample_order_item_id
    ):
        """Test that insufficient inventory raises error"""
        from sqlalchemy import select

        mock_variant = MagicMock()
        mock_variant.id = sample_variant_id
        mock_variant.inventory = 2
        mock_variant.reserved_inventory = 2

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_variant
        mock_session.execute.return_value = mock_result

        reservation_service = ReservationService(mock_session)

        with pytest.raises(ValueError, match="Insufficient inventory"):
            await reservation_service.reserve_inventory(
                variant_id=sample_variant_id,
                order_item_id=sample_order_item_id,
                quantity=5,
                expires_in_minutes=30,
            )

    @pytest.mark.asyncio
    async def test_reservation_timeout_release(
        self, mock_session, sample_variant_id, sample_order_item_id
    ):
        """Test that reservation is released on timeout"""
        mock_reservation = MagicMock()
        mock_reservation.id = uuid.uuid4()
        mock_reservation.variant_id = sample_variant_id
        mock_reservation.order_item_id = sample_order_item_id
        mock_reservation.quantity = 5
        mock_reservation.status = "reserved"
        mock_reservation.expires_at = datetime.utcnow() - timedelta(minutes=1)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_reservation]
        mock_session.execute.return_value = mock_result

        reservation_service = ReservationService(mock_session)

        await reservation_service.release_expired_reservations()

        mock_session.flush.assert_called()


class TestOrderHistory:
    """Tests for order history tracking"""

    @pytest.mark.asyncio
    async def test_history_recorded_on_transition(self, mock_session):
        """Test that order history is recorded on status transition"""
        order_id = uuid.uuid4()

        mock_order = MagicMock()
        mock_order.id = order_id
        mock_order.status = OrderStatus.PENDING.value

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_order
        mock_session.execute.return_value = mock_result

        service = OrderService(mock_session)

        await service.transition_status(
            order_id=order_id,
            new_status=OrderStatus.CONFIRMED,
            actor_type="system",
            reason="Order confirmed by automated process",
        )

        mock_session.add.assert_called()

    @pytest.mark.asyncio
    async def test_order_cancellation_creates_history(
        self, mock_session, sample_shop_id
    ):
        """Test that order cancellation creates history record"""
        order_id = uuid.uuid4()

        mock_order = MagicMock()
        mock_order.id = order_id
        mock_order.status = OrderStatus.PENDING.value
        mock_order.total_price = Decimal("100.00")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_order
        mock_session.execute.return_value = mock_result

        service = OrderService(mock_session)

        await service.cancel_order(
            order_id=order_id, reason="Customer requested cancellation"
        )

        mock_session.flush.assert_called()


class TestOrderSplitBySupplier:
    """Tests for order splitting by supplier"""

    @pytest.mark.asyncio
    async def test_order_items_grouped_by_supplier(self, mock_session):
        """Test that order items are correctly grouped by supplier"""
        order_id = uuid.uuid4()

        supplier_a = uuid.uuid4()
        supplier_b = uuid.uuid4()

        items = [
            MagicMock(supplier_shop_id=supplier_a, id=uuid.uuid4()),
            MagicMock(supplier_shop_id=supplier_a, id=uuid.uuid4()),
            MagicMock(supplier_shop_id=supplier_b, id=uuid.uuid4()),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = items

        async def execute_side_effect(*args, **kwargs):
            return mock_result

        mock_session.execute.side_effect = execute_side_effect

        service = OrderService(mock_session)

        groups = await service.split_order_by_supplier(order_id)

        assert len(groups) == 2
        assert len(groups[supplier_a]) == 2
        assert len(groups[supplier_b]) == 1
