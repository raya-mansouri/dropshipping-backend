"""
Payment Service
===============
Handles payment lifecycle: creation, escrow, payout, refund.

Flow: Order Created → Inventory Reserved → Seller Pays → Platform Holds (Escrow) →
      Supplier Ships → Delivered → 72h Dispute Window → Release to Supplier
"""
import structlog
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional, List

from sqlalchemy import select, and_, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Payment, PaymentStatus, Refund, SupplierPayout
from ..orders.models import Order, OrderItem
from src.core.events.base import DomainEvent
from src.core.events.publisher import EventPublisher
from src.core.events.payment import (
    PaymentReceived,
    PaymentToEscrow,
    RefundInitiated,
    RefundCompleted,
)

logger = structlog.get_logger(__name__)

# Default platform fee percentage
DEFAULT_PLATFORM_FEE_PERCENT = Decimal("5.0")

# Dispute window durations
NORMAL_DISPUTE_WINDOW_HOURS = 72
HIGH_VALUE_DISPUTE_WINDOW_DAYS = 7
HIGH_VALUE_THRESHOLD = Decimal("10000000")  # 10M IRR


class PaymentService:
    """Service for managing payment lifecycle."""

    def __init__(
        self,
        session: AsyncSession,
        event_publisher: Optional[EventPublisher] = None,
    ):
        self.session = session
        self._event_publisher = event_publisher

    async def _publish_event(self, event: DomainEvent) -> None:
        """Safely publish domain event. Non-blocking - failures are logged but don't raise."""
        if self._event_publisher is None:
            return
        try:
            await self._event_publisher.publish(topic="events", event=event)
        except Exception as e:
            logger.warning("failed_to_publish_event", event_type=event.event_type, error=str(e))

    async def create_payment(
        self,
        order_id,
        gateway: str = "idpay",
    ) -> Payment:
        """Create a payment record for an order."""
        # Fetch order with items
        order_stmt = select(Order).where(Order.id == order_id)
        order_result = await self.session.execute(order_stmt)
        order = order_result.scalar_one_or_none()
        if not order:
            raise ValueError(f"Order {order_id} not found")

        # Fetch order items
        items_stmt = select(OrderItem).where(OrderItem.order_id == order_id)
        items_result = await self.session.execute(items_stmt)
        items = items_result.scalars().all()

        # Calculate totals
        total_seller_amount = sum(
            item.seller_price * item.quantity for item in items
        )
        total_supplier_amount = sum(
            item.supplier_price * item.quantity for item in items
        )
        platform_fee = total_seller_amount * (DEFAULT_PLATFORM_FEE_PERCENT / 100)
        shipping_cost = sum(item.shipping_price or 0 for item in items)

        payment = Payment(
            order_id=order_id,
            seller_paid_amount=total_seller_amount,
            supplier_payable_amount=total_supplier_amount,
            platform_fee=platform_fee,
            shipping_cost=shipping_cost,
            gateway=gateway,
            status=PaymentStatus.PENDING.value,
        )
        self.session.add(payment)
        await self.session.flush()

        logger.info(
            "payment_created",
            payment_id=str(payment.id),
            order_id=str(order_id),
            seller_amount=str(total_seller_amount),
            supplier_amount=str(total_supplier_amount),
            platform_fee=str(platform_fee),
        )
        return payment

    async def mark_seller_paid(
        self,
        payment_id,
        gateway_transaction_id: str,
    ) -> Payment:
        """Mark payment as seller-paid and enter escrow."""
        stmt = select(Payment).where(Payment.id == payment_id)
        result = await self.session.execute(stmt)
        payment = result.scalar_one_or_none()
        if not payment:
            raise ValueError(f"Payment {payment_id} not found")

        payment.status = PaymentStatus.ESCROW.value
        payment.paid_at = datetime.now(timezone.utc)
        payment.escrow_started_at = datetime.now(timezone.utc)
        payment.gateway_transaction_id = gateway_transaction_id

        await self.session.flush()

        # Publish payment received / escrow event
        event = PaymentReceived(
            order_id=payment.order_id,
            payment_id=payment.id,
            amount=float(payment.seller_paid_amount),
            gateway=payment.gateway or "unknown",
        )
        await self._publish_event(event)

        escrow_event = PaymentToEscrow(
            order_id=payment.order_id,
            payment_id=payment.id,
            amount=float(payment.seller_paid_amount),
        )
        await self._publish_event(escrow_event)

        logger.info("payment_moved_to_escrow", payment_id=str(payment_id))
        return payment

    async def create_payout_after_delivery(
        self,
        order_item_id,
        delivery_confirmed_by: str = "auto",
    ) -> Optional[SupplierPayout]:
        """Create supplier payout after delivery confirmation."""
        # Find the payment for this order item
        item_stmt = select(OrderItem).where(OrderItem.id == order_item_id)
        item_result = await self.session.execute(item_stmt)
        item = item_result.scalar_one_or_none()
        if not item:
            return None

        payment_stmt = select(Payment).where(Payment.order_id == item.order_id)
        payment_result = await self.session.execute(payment_stmt)
        payment = payment_result.scalar_one_or_none()
        if not payment or payment.status != PaymentStatus.ESCROW.value:
            return None

        # Determine dispute window
        is_high_value = item.seller_price * item.quantity >= HIGH_VALUE_THRESHOLD
        dispute_hours = (
            HIGH_VALUE_DISPUTE_WINDOW_DAYS * 24
            if is_high_value
            else NORMAL_DISPUTE_WINDOW_HOURS
        )

        supplier_amount = item.supplier_price * item.quantity
        payout = SupplierPayout(
            supplier_id=item.supplier_shop_id,
            order_item_id=order_item_id,
            payment_id=payment.id,
            amount=supplier_amount,
            status="pending",
            release_conditions_met=True,
            delivery_confirmed_at=datetime.now(timezone.utc),
            dispute_window_ends_at=datetime.now(timezone.utc) + timedelta(hours=dispute_hours),
        )
        self.session.add(payout)
        await self.session.flush()

        logger.info(
            "payout_created",
            payout_id=str(payout.id),
            supplier_shop_id=str(item.supplier_shop_id),
            amount=str(supplier_amount),
            dispute_window_hours=dispute_hours,
        )
        return payout

    async def release_mature_payouts(self) -> List[SupplierPayout]:
        """Release payouts where dispute window has expired."""
        now = datetime.now(timezone.utc)

        stmt = (
            select(SupplierPayout)
            .where(
                and_(
                    SupplierPayout.status == "pending",
                    SupplierPayout.release_conditions_met.is_(True),
                    SupplierPayout.dispute_window_ends_at <= now,
                )
            )
        )
        result = await self.session.execute(stmt)
        mature_payouts = result.scalars().all()

        if not mature_payouts:
            return []

        # Batch-update all mature payouts in a single UPDATE query
        payout_ids = [p.id for p in mature_payouts]
        payment_ids = {p.payment_id for p in mature_payouts if p.payment_id}

        await self.session.execute(
            sa_update(SupplierPayout)
            .where(SupplierPayout.id.in_(payout_ids))
            .values(status="completed", released_at=now)
        )

        # Batch-update parent payments in a single UPDATE query
        if payment_ids:
            await self.session.execute(
                sa_update(Payment)
                .where(Payment.id.in_(payment_ids))
                .values(
                    status=PaymentStatus.SUPPLIER_PAID.value,
                    supplier_paid_at=now,
                )
            )

        await self.session.flush()

        # Build return list with updated attributes for ORM consistency
        released = []
        for payout in mature_payouts:
            payout.status = "completed"
            payout.released_at = now
            released.append(payout)

        logger.info("mature_payouts_released", count=len(released))
        return released

    async def create_refund(
        self,
        payment_id,
        order_item_id,
        amount: Decimal,
        refund_type: str = "full",
        reason: str = None,
        requested_by: str = "seller",
    ) -> Refund:
        """Create a refund request."""
        refund = Refund(
            payment_id=payment_id,
            order_item_id=order_item_id,
            amount=amount,
            refund_type=refund_type,
            reason=reason,
            requested_by=requested_by,
            status="requested",
        )
        self.session.add(refund)
        await self.session.flush()

        # Publish refund initiated event
        event = RefundInitiated(
            payment_id=payment_id,
            order_item_id=order_item_id,
            amount=float(amount),
            reason=reason or "not_specified",
        )
        await self._publish_event(event)

        logger.info(
            "refund_created",
            refund_id=str(refund.id),
            payment_id=str(payment_id),
            amount=str(amount),
        )
        return refund

    async def process_refund(self, refund_id, approved_by) -> Refund:
        """Approve and process a refund."""
        stmt = select(Refund).where(Refund.id == refund_id)
        result = await self.session.execute(stmt)
        refund = result.scalar_one_or_none()
        if not refund:
            raise ValueError(f"Refund {refund_id} not found")

        refund.status = "completed"
        refund.approved_by = approved_by
        refund.approved_at = datetime.now(timezone.utc)
        refund.completed_at = datetime.now(timezone.utc)

        # Update payment status
        if refund.payment_id:
            pay_stmt = select(Payment).where(Payment.id == refund.payment_id)
            pay_result = await self.session.execute(pay_stmt)
            payment = pay_result.scalar_one_or_none()
            if payment:
                payment.status = PaymentStatus.REFUNDED.value
                payment.refunded_at = datetime.now(timezone.utc)

        await self.session.flush()

        # Publish refund completed event
        event = RefundCompleted(
            refund_id=refund.id,
            payment_id=refund.payment_id,
            order_item_id=refund.order_item_id,
            amount=float(refund.amount),
        )
        await self._publish_event(event)

        return refund
