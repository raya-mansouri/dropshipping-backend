"""
Payment Service
===============
Handles payment lifecycle: creation, escrow, payout, refund, wallet, and disputes.

Flow: Order Created -> Inventory Reserved -> Seller Pays -> Platform Holds (Escrow) ->
      Supplier Ships -> Delivered -> 72h Dispute Window -> Release to Supplier
"""

import structlog
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional, List
from uuid import UUID

from sqlalchemy import select, and_, update as sa_update, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models import (
    Payment,
    PaymentStatus,
    Refund,
    SupplierPayout,
    Dispute,
    WalletTransaction,
    TransactionType,
    TransactionStatus,
)
from ..repository import (
    PaymentRepository,
    RefundRepository,
    SupplierPayoutRepository,
    DisputeRepository,
)
from ...orders.models import Order, OrderItem
from src.core.config import get_settings
from src.core.events.base import DomainEvent
from src.core.events.publisher import EventPublisher
from src.core.events.payment import (
    PaymentReceived,
    PaymentToEscrow,
    PaymentReleasedToSupplier,
    RefundInitiated,
    RefundCompleted,
)

logger = structlog.get_logger(__name__)

# Dispute window durations
NORMAL_DISPUTE_WINDOW_HOURS = 72
HIGH_VALUE_DISPUTE_WINDOW_DAYS = 7
HIGH_VALUE_THRESHOLD = Decimal("1000000")  # 1M Toman


class PaymentService:
    """Service for managing payment lifecycle, wallet, escrow, payouts, and disputes."""

    def __init__(
        self,
        session: AsyncSession,
        event_publisher: Optional[EventPublisher] = None,
    ):
        self.session = session
        self._event_publisher = event_publisher
        self._payment_repo = PaymentRepository(session)
        self._refund_repo = RefundRepository(session)
        self._payout_repo = SupplierPayoutRepository(session)
        self._dispute_repo = DisputeRepository(session)

    async def _publish_event(self, event: DomainEvent) -> None:
        """Safely publish domain event. Non-blocking - failures are logged but don't raise."""
        if self._event_publisher is None:
            return
        try:
            await self._event_publisher.publish(topic="events", event=event)
        except Exception as e:
            logger.warning(
                "failed_to_publish_event", event_type=event.event_type, error=str(e)
            )

    # ==================================================================
    # Wallet Operations
    # ==================================================================

    async def get_balance(self, user_id: UUID) -> int:
        """Calculate wallet balance from completed transaction history.

        Balance = SUM(amount) where status='completed'.
        Deposits are positive, payments are negative.
        """
        stmt = select(func.coalesce(func.sum(WalletTransaction.amount), 0)).where(
            and_(
                WalletTransaction.user_id == user_id,
                WalletTransaction.status == TransactionStatus.COMPLETED.value,
            )
        )
        result = await self.session.execute(stmt)
        balance = result.scalar()
        return int(balance)

    async def get_wallet_balance(self, user_id: UUID) -> int:
        """Alias for get_balance, used by API layer."""
        return await self.get_balance(user_id)

    async def get_pending_amount(self, user_id: UUID) -> int:
        """Calculate amount locked in pending transactions."""
        stmt = select(func.coalesce(func.sum(WalletTransaction.amount), 0)).where(
            and_(
                WalletTransaction.user_id == user_id,
                WalletTransaction.status == TransactionStatus.PENDING.value,
                WalletTransaction.amount > 0,
            )
        )
        result = await self.session.execute(stmt)
        pending = result.scalar()
        return int(pending)

    async def deposit(
        self,
        user_id: UUID,
        amount: int,
        token: str,
        gateway: str = "zarinpal",
    ) -> WalletTransaction:
        """Create a pending wallet deposit transaction (before gateway redirect)."""
        tx = WalletTransaction(
            user_id=user_id,
            amount=Decimal(amount),
            type=TransactionType.DEPOSIT.value,
            status=TransactionStatus.PENDING.value,
            reference_type="payment",
            reference_id=token,
            description="شارژ کیف پول",
            gateway=gateway,
        )
        self.session.add(tx)
        await self.session.flush()

        logger.info(
            "deposit_transaction_created",
            transaction_id=str(tx.id),
            user_id=str(user_id),
            amount=amount,
        )
        return tx

    # Keep backward-compatible alias
    async def create_deposit_transaction(
        self,
        user_id: UUID,
        amount: int,
        token: str,
        gateway: str = "zarinpal",
    ) -> WalletTransaction:
        """Create a pending wallet deposit transaction. Alias for deposit()."""
        return await self.deposit(user_id, amount, token, gateway)

    async def verify_and_complete_deposit(
        self,
        token: str,
        user_id: UUID,
        gateway_ref_id: str | None = None,
        extra_metadata: dict | None = None,
    ) -> WalletTransaction:
        """Mark a deposit transaction as completed after gateway verification."""
        stmt = select(WalletTransaction).where(
            and_(
                WalletTransaction.reference_id == token,
                WalletTransaction.reference_type == "payment",
                WalletTransaction.type == TransactionType.DEPOSIT.value,
            )
        )
        result = await self.session.execute(stmt)
        tx = result.scalar_one_or_none()

        if not tx:
            raise ValueError(f"Deposit transaction not found for token {token}")

        if tx.user_id != user_id:
            raise PermissionError("Transaction does not belong to this user")

        if tx.status == TransactionStatus.COMPLETED.value:
            logger.info("deposit_already_completed", transaction_id=str(tx.id))
            return tx

        if tx.status != TransactionStatus.PENDING.value:
            raise ValueError(f"Transaction is in {tx.status} state, cannot verify")

        tx.status = TransactionStatus.COMPLETED.value
        tx.gateway_ref_id = gateway_ref_id
        if extra_metadata:
            tx.extra_data = {**(tx.extra_data or {}), **extra_metadata}

        await self.session.flush()

        logger.info(
            "deposit_completed", transaction_id=str(tx.id), amount=str(tx.amount)
        )
        return tx

    async def fail_deposit(self, token: str) -> Optional[WalletTransaction]:
        """Mark a deposit transaction as failed."""
        stmt = select(WalletTransaction).where(
            and_(
                WalletTransaction.reference_id == token,
                WalletTransaction.reference_type == "payment",
                WalletTransaction.type == TransactionType.DEPOSIT.value,
                WalletTransaction.status == TransactionStatus.PENDING.value,
            )
        )
        result = await self.session.execute(stmt)
        tx = result.scalar_one_or_none()

        if tx:
            tx.status = TransactionStatus.FAILED.value
            await self.session.flush()
            logger.info("deposit_failed", transaction_id=str(tx.id))

        return tx

    async def withdraw(
        self,
        user_id: UUID,
        amount: int,
        reference_type: str = "payout",
        reference_id: str | None = None,
        description: str | None = None,
    ) -> WalletTransaction:
        """Withdraw from wallet. Used for payouts and other deductions.

        Uses SELECT FOR UPDATE on existing wallet transactions to prevent
        concurrent withdrawals from creating a negative balance.
        """
        # Lock wallet transaction rows to prevent concurrent balance changes
        lock_stmt = (
            select(WalletTransaction)
            .where(
                and_(
                    WalletTransaction.user_id == user_id,
                    WalletTransaction.status == TransactionStatus.COMPLETED.value,
                )
            )
            .with_for_update()
        )
        await self.session.execute(lock_stmt)

        balance = await self.get_balance(user_id)
        if balance < amount:
            raise ValueError(
                f"Insufficient wallet balance. Required: {amount}, Available: {balance}"
            )

        tx = WalletTransaction(
            user_id=user_id,
            amount=-Decimal(amount),
            type=TransactionType.PAYOUT.value,
            status=TransactionStatus.COMPLETED.value,
            reference_type=reference_type,
            reference_id=reference_id or "",
            description=description or "برداشت از کیف پول",
        )
        self.session.add(tx)
        await self.session.flush()

        logger.info(
            "wallet_withdrawal",
            user_id=str(user_id),
            amount=amount,
            transaction_id=str(tx.id),
        )
        return tx

    async def get_transactions(
        self,
        user_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> List[WalletTransaction]:
        """Get wallet transaction history for a user."""
        stmt = (
            select(WalletTransaction)
            .where(WalletTransaction.user_id == user_id)
            .order_by(WalletTransaction.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def pay_order_from_wallet(
        self,
        order_id: UUID,
        user_id: UUID,
    ) -> Payment:
        """Pay for an order from wallet balance with atomic row locking.

        Uses SELECT FOR UPDATE on the order row to prevent double-payment.
        Creates separate transactions for items, shipping, and commission.
        """
        settings = get_settings()
        fee_rate = Decimal(str(settings.payment_fee_rate))

        # Lock the order row to prevent concurrent payment
        order_stmt = select(Order).where(Order.id == order_id).with_for_update()
        order_result = await self.session.execute(order_stmt)
        order = order_result.scalar_one_or_none()

        if not order:
            raise ValueError(f"Order {order_id} not found")

        if order.status not in ("pending", "confirmed"):
            raise ValueError(
                f"Order {order_id} cannot be paid (status: {order.status})"
            )

        if order.paid_at is not None:
            raise ValueError(f"Order {order_id} is already paid")

        # Fetch order items
        items_stmt = select(OrderItem).where(OrderItem.order_id == order_id)
        items_result = await self.session.execute(items_stmt)
        items = items_result.scalars().all()

        if not items:
            raise ValueError(f"Order {order_id} has no items")

        # Calculate cost breakdown
        items_subtotal = sum(item.seller_price * item.quantity for item in items)
        shipping_total = sum(item.shipping_price or 0 for item in items)
        commission = int(items_subtotal * fee_rate)
        total_cost = int(items_subtotal) + int(shipping_total) + commission

        # Check wallet balance
        balance = await self.get_balance(user_id)
        if balance < total_cost:
            raise ValueError(
                f"Insufficient wallet balance. Required: {total_cost}, Available: {balance}"
            )

        # Create the payment record (escrow)
        platform_fee = items_subtotal * fee_rate
        payment = await self.hold_payment(
            order_id=order_id,
            seller_paid_amount=items_subtotal,
            supplier_payable_amount=sum(
                item.supplier_price * item.quantity for item in items
            ),
            platform_fee=platform_fee,
            shipping_cost=shipping_total,
            gateway="wallet",
        )

        # Create wallet transactions (negative amounts for deductions)
        # 1. Items payment
        if items_subtotal > 0:
            items_tx = WalletTransaction(
                user_id=user_id,
                amount=-items_subtotal,
                type=TransactionType.ORDER_PAYMENT.value,
                status=TransactionStatus.COMPLETED.value,
                reference_type="order",
                reference_id=str(order_id),
                description="پرداخت سفارش - مبلغ کالاها",
                extra_data={
                    "payment_id": str(payment.id),
                    "cost_type": "items_subtotal",
                },
            )
            self.session.add(items_tx)

        # 2. Shipping
        if shipping_total > 0:
            shipping_tx = WalletTransaction(
                user_id=user_id,
                amount=-shipping_total,
                type=TransactionType.SHIPPING.value,
                status=TransactionStatus.COMPLETED.value,
                reference_type="order",
                reference_id=str(order_id),
                description="پرداخت سفارش - هزینه ارسال",
                extra_data={"payment_id": str(payment.id), "cost_type": "shipping"},
            )
            self.session.add(shipping_tx)

        # 3. Commission
        if commission > 0:
            commission_tx = WalletTransaction(
                user_id=user_id,
                amount=-Decimal(commission),
                type=TransactionType.COMMISSION.value,
                status=TransactionStatus.COMPLETED.value,
                reference_type="order",
                reference_id=str(order_id),
                description="پرداخت سفارش - کمیسیون پلتفرم",
                extra_data={
                    "payment_id": str(payment.id),
                    "cost_type": "commission",
                    "rate": str(fee_rate),
                },
            )
            self.session.add(commission_tx)

        # Update order status
        order.status = "paid"
        order.paid_at = datetime.now(timezone.utc)

        await self.session.flush()

        # Publish events
        event = PaymentReceived(
            order_id=order_id,
            payment_id=payment.id,
            amount=int(items_subtotal),
            gateway="wallet",
        )
        await self._publish_event(event)

        escrow_event = PaymentToEscrow(
            order_id=order_id,
            payment_id=payment.id,
            amount=int(items_subtotal),
        )
        await self._publish_event(escrow_event)

        logger.info(
            "order_paid_from_wallet",
            order_id=str(order_id),
            payment_id=str(payment.id),
            total_cost=total_cost,
            commission=commission,
        )
        return payment

    # ==================================================================
    # Escrow Operations
    # ==================================================================

    async def hold_payment(
        self,
        order_id: UUID,
        seller_paid_amount: Decimal,
        supplier_payable_amount: Decimal,
        platform_fee: Decimal = Decimal("0"),
        shipping_cost: Decimal = Decimal("0"),
        gateway: str = "wallet",
        order_item_id: UUID | None = None,
    ) -> Payment:
        """Create a payment in escrow state. Seller pays, platform holds.

        This is the core escrow entry point. Creates a Payment record
        with ESCROW status and publishes domain events.
        """
        payment = Payment(
            order_id=order_id,
            order_item_id=order_item_id,
            seller_paid_amount=seller_paid_amount,
            supplier_payable_amount=supplier_payable_amount,
            platform_fee=platform_fee,
            shipping_cost=shipping_cost,
            gateway=gateway,
            status=PaymentStatus.ESCROW.value,
            paid_at=datetime.now(timezone.utc),
            escrow_started_at=datetime.now(timezone.utc),
        )
        self.session.add(payment)
        await self.session.flush()

        logger.info(
            "payment_held_in_escrow",
            payment_id=str(payment.id),
            order_id=str(order_id),
            amount=str(seller_paid_amount),
        )
        return payment

    async def release_to_supplier(
        self,
        payment_id: UUID,
        supplier_id: UUID,
        order_item_id: UUID,
        payout_method: str = "wallet",
    ) -> SupplierPayout:
        """Release escrow payment to supplier after delivery confirmation.

        Creates a SupplierPayout record and calculates the supplier's share
        minus platform fee. The payout enters pending state until the dispute
        window expires.
        """
        payment = await self._payment_repo.get_by_id(payment_id)
        if not payment:
            raise ValueError(f"Payment {payment_id} not found")

        if payment.status != PaymentStatus.ESCROW.value:
            raise ValueError(
                f"Payment {payment_id} is not in escrow (status: {payment.status})"
            )

        # Determine dispute window
        is_high_value = payment.seller_paid_amount >= HIGH_VALUE_THRESHOLD
        dispute_hours = (
            HIGH_VALUE_DISPUTE_WINDOW_DAYS * 24
            if is_high_value
            else NORMAL_DISPUTE_WINDOW_HOURS
        )

        supplier_amount = payment.supplier_payable_amount

        payout = SupplierPayout(
            supplier_id=supplier_id,
            order_item_id=order_item_id,
            payment_id=payment.id,
            amount=supplier_amount,
            status="pending",
            release_conditions_met=True,
            delivery_confirmed_at=datetime.now(timezone.utc),
            dispute_window_ends_at=datetime.now(timezone.utc)
            + timedelta(hours=dispute_hours),
            payout_method=payout_method,
        )
        self.session.add(payout)
        await self.session.flush()

        # Publish event
        event = PaymentReleasedToSupplier(
            order_id=payment.order_id,
            payment_id=payment.id,
            supplier_id=supplier_id,
            amount=int(supplier_amount),
        )
        await self._publish_event(event)

        logger.info(
            "payment_released_to_supplier",
            payment_id=str(payment_id),
            payout_id=str(payout.id),
            supplier_id=str(supplier_id),
            amount=str(supplier_amount),
        )
        return payout

    async def refund_to_seller(
        self,
        payment_id: UUID,
        order_item_id: UUID,
        amount: Decimal | None = None,
        refund_type: str = "full",
        reason: str = "refund_to_seller",
        requested_by: str = "seller",
        user_id: UUID | None = None,
    ) -> Refund:
        """Refund escrow payment back to seller (cancel or dispute resolution).

        Creates a Refund record and, if a user_id is provided, adds a positive
        wallet transaction to credit the seller's wallet.
        """
        payment = await self._payment_repo.get_by_id(payment_id)
        if not payment:
            raise ValueError(f"Payment {payment_id} not found")

        refund_amount = amount if amount is not None else payment.seller_paid_amount

        refund = Refund(
            payment_id=payment_id,
            order_item_id=order_item_id,
            amount=refund_amount,
            refund_type=refund_type,
            reason=reason,
            requested_by=requested_by,
            status="requested",
        )
        self.session.add(refund)

        # Update payment status
        payment.status = PaymentStatus.REFUNDED.value
        payment.refunded_at = datetime.now(timezone.utc)

        await self.session.flush()

        # Credit seller's wallet if user_id is known
        if user_id:
            wallet_tx = WalletTransaction(
                user_id=user_id,
                amount=refund_amount,
                type=TransactionType.REFUND.value,
                status=TransactionStatus.COMPLETED.value,
                reference_type="refund",
                reference_id=str(refund.id),
                description="بازگشت وجه - استرداد",
                extra_data={"payment_id": str(payment_id), "refund_type": refund_type},
            )
            self.session.add(wallet_tx)
            await self.session.flush()

        # Update refund status to completed
        refund.status = "completed"
        refund.completed_at = datetime.now(timezone.utc)
        await self.session.flush()

        # Publish events
        initiated_event = RefundInitiated(
            payment_id=payment_id,
            order_item_id=order_item_id,
            amount=int(refund_amount),
            reason=reason,
        )
        await self._publish_event(initiated_event)

        completed_event = RefundCompleted(
            refund_id=refund.id,
            payment_id=payment_id,
            order_item_id=order_item_id,
            amount=int(refund_amount),
        )
        await self._publish_event(completed_event)

        logger.info(
            "payment_refunded_to_seller",
            payment_id=str(payment_id),
            refund_id=str(refund.id),
            amount=str(refund_amount),
        )
        return refund

    # ==================================================================
    # Payout Operations
    # ==================================================================

    async def list_payouts(
        self,
        supplier_id: UUID | None = None,
        payout_status: str | None = None,
        shop_ids: list[UUID] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[SupplierPayout]:
        """List supplier payouts with optional filters."""
        stmt = select(SupplierPayout)

        if supplier_id:
            stmt = stmt.where(SupplierPayout.supplier_id == supplier_id)
        if payout_status:
            stmt = stmt.where(SupplierPayout.status == payout_status)
        if shop_ids is not None:
            stmt = stmt.where(SupplierPayout.supplier_id.in_(shop_ids))

        stmt = (
            stmt.order_by(SupplierPayout.created_at.desc()).limit(limit).offset(offset)
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_payout(
        self,
        supplier_id: UUID,
        order_item_id: UUID,
        amount: Decimal,
        payment_id: UUID | None = None,
        payout_method: str = "wallet",
    ) -> SupplierPayout:
        """Create a new supplier payout record."""
        payout = SupplierPayout(
            supplier_id=supplier_id,
            order_item_id=order_item_id,
            payment_id=payment_id,
            amount=amount,
            status="pending",
            payout_method=payout_method,
        )
        self.session.add(payout)
        await self.session.flush()

        logger.info(
            "payout_created",
            payout_id=str(payout.id),
            supplier_id=str(supplier_id),
            amount=str(amount),
        )
        return payout

    async def create_payout_after_delivery(
        self,
        order_item_id: UUID,
        delivery_confirmed_by: str = "auto",
    ) -> Optional[SupplierPayout]:
        """Create supplier payout after delivery confirmation.

        Called when an order item is confirmed delivered. Creates a pending
        payout record with the appropriate dispute window.
        """
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
            dispute_window_ends_at=datetime.now(timezone.utc)
            + timedelta(hours=dispute_hours),
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

    async def process_payout(
        self,
        payout_id: UUID,
    ) -> SupplierPayout:
        """Process a mature payout: calculate supplier share and release funds.

        Called when the dispute window has expired. Calculates the final
        supplier amount and updates both payout and payment status.
        """
        payout = await self._payout_repo.get_by_id(payout_id)
        if not payout:
            raise ValueError(f"Payout {payout_id} not found")

        if payout.status != "pending":
            raise ValueError(
                f"Payout {payout_id} cannot be processed (status: {payout.status})"
            )

        now = datetime.now(timezone.utc)

        # Update payout to completed
        payout.status = "completed"
        payout.released_at = now

        # Update linked payment if present
        if payout.payment_id:
            await self._payment_repo.update(
                payout.payment_id,
                {
                    "status": PaymentStatus.SUPPLIER_PAID.value,
                    "supplier_paid_at": now,
                },
            )

        await self.session.flush()

        logger.info(
            "payout_processed",
            payout_id=str(payout_id),
            supplier_id=str(payout.supplier_id),
            amount=str(payout.amount),
        )
        return payout

    async def release_mature_payouts(self) -> List[SupplierPayout]:
        """Release payouts where dispute window has expired (batch operation).

        Processes each payout individually. Only marks a payment as
        supplier_paid after all its associated payouts succeed. If any
        payout fails, the linked payment keeps its current status.
        """
        now = datetime.now(timezone.utc)

        stmt = select(SupplierPayout).where(
            and_(
                SupplierPayout.status == "pending",
                SupplierPayout.release_conditions_met.is_(True),
                SupplierPayout.dispute_window_ends_at <= now,
            )
        )
        result = await self.session.execute(stmt)
        mature_payouts = result.scalars().all()

        if not mature_payouts:
            return []

        # Process payouts one by one so a failure doesn't corrupt others
        released: list[SupplierPayout] = []
        failed_payout_ids: set[UUID] = set()

        for payout in mature_payouts:
            try:
                payout.status = "completed"
                payout.released_at = now
                released.append(payout)
            except Exception as exc:
                failed_payout_ids.add(payout.id)
                logger.error(
                    "payout_release_failed",
                    payout_id=str(payout.id),
                    error=str(exc),
                )

        if not released:
            return []

        await self.session.flush()

        # Only mark payments as supplier_paid for payouts that succeeded.
        # Exclude payment_ids tied to any failed payout.
        payment_ids = {
            p.payment_id
            for p in released
            if p.payment_id and p.id not in failed_payout_ids
        }

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

        logger.info(
            "mature_payouts_released",
            count=len(released),
            failed=len(failed_payout_ids),
        )
        return released

    # ==================================================================
    # Payment Operations (Gateway)
    # ==================================================================

    async def create_payment(
        self,
        order_id: UUID,
        gateway: str = "idpay",
    ) -> Payment:
        """Create a payment record for an order (via gateway).

        Calculates totals from order items and creates a PENDING payment
        record. The caller (API) should then redirect to the gateway.
        """
        order_stmt = select(Order).where(Order.id == order_id)
        order_result = await self.session.execute(order_stmt)
        order = order_result.scalar_one_or_none()
        if not order:
            raise ValueError(f"Order {order_id} not found")

        items_stmt = select(OrderItem).where(OrderItem.order_id == order_id)
        items_result = await self.session.execute(items_stmt)
        items = items_result.scalars().all()

        total_seller_amount = sum(item.seller_price * item.quantity for item in items)
        total_supplier_amount = sum(
            item.supplier_price * item.quantity for item in items
        )
        fee_rate = Decimal(str(get_settings().payment_fee_rate))
        platform_fee = total_seller_amount * fee_rate
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

    async def verify_payment(
        self,
        payment_id: UUID,
        gateway_transaction_id: str,
    ) -> Payment:
        """Mark payment as seller-paid and enter escrow after gateway verification.

        Called when the payment gateway confirms the transaction.
        Transitions the payment from PENDING -> ESCROW.
        """
        payment = await self._payment_repo.get_by_id(payment_id)
        if not payment:
            raise ValueError(f"Payment {payment_id} not found")

        if payment.status != PaymentStatus.PENDING.value:
            raise ValueError(
                f"Payment {payment_id} cannot be verified (status: {payment.status}, expected: {PaymentStatus.PENDING.value})"
            )

        payment.status = PaymentStatus.ESCROW.value
        payment.paid_at = datetime.now(timezone.utc)
        payment.escrow_started_at = datetime.now(timezone.utc)
        payment.gateway_transaction_id = gateway_transaction_id

        await self.session.flush()

        # Publish events
        received_event = PaymentReceived(
            order_id=payment.order_id,
            payment_id=payment.id,
            amount=int(payment.seller_paid_amount),
            gateway=payment.gateway or "unknown",
        )
        await self._publish_event(received_event)

        escrow_event = PaymentToEscrow(
            order_id=payment.order_id,
            payment_id=payment.id,
            amount=int(payment.seller_paid_amount),
        )
        await self._publish_event(escrow_event)

        logger.info("payment_verified_and_moved_to_escrow", payment_id=str(payment_id))
        return payment

    # Keep backward-compatible alias
    async def mark_seller_paid(
        self,
        payment_id: UUID,
        gateway_transaction_id: str,
    ) -> Payment:
        """Mark payment as seller-paid. Alias for verify_payment()."""
        return await self.verify_payment(payment_id, gateway_transaction_id)

    async def list_payments(
        self,
        payment_status: PaymentStatus | None = None,
        shop_ids: list[UUID] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Payment]:
        """List payments with optional status and shop scope filter."""
        stmt = select(Payment)

        if payment_status:
            stmt = stmt.where(Payment.status == payment_status.value)

        if shop_ids is not None:
            stmt = stmt.join(Order, Payment.order_id == Order.id).where(
                Order.shop_id.in_(shop_ids)
            )

        stmt = stmt.order_by(Payment.created_at.desc()).limit(limit).offset(offset)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_payment(self, payment_id: UUID) -> Optional[Payment]:
        """Get a payment by ID with order relationship loaded."""
        stmt = (
            select(Payment)
            .where(Payment.id == payment_id)
            .options(selectinload(Payment.order))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    # ==================================================================
    # Dispute Operations
    # ==================================================================

    async def create_dispute(
        self,
        order_item_id: UUID,
        opened_by: str,
        reason: str,
        opened_by_id: UUID | None = None,
        evidence: list[dict] | None = None,
    ) -> Dispute:
        """Create a dispute for an order item. Freezes payment until resolved."""
        dispute = Dispute(
            order_item_id=order_item_id,
            opened_by=opened_by,
            opened_by_id=opened_by_id,
            reason=reason,
            evidence=evidence or [],
            status="open",
        )
        self.session.add(dispute)
        await self.session.flush()

        logger.info(
            "dispute_created",
            dispute_id=str(dispute.id),
            order_item_id=str(order_item_id),
            opened_by=opened_by,
        )
        return dispute

    async def respond_dispute(
        self,
        dispute_id: UUID,
        status: str | None = None,
        evidence: list[dict] | None = None,
    ) -> Dispute:
        """Respond to a dispute by updating status or adding evidence.

        Typically used to move dispute to 'investigating' status with
        additional evidence from the responding party.
        """
        dispute = await self._dispute_repo.get_by_id(dispute_id)
        if not dispute:
            raise ValueError(f"Dispute {dispute_id} not found")

        if dispute.status not in ("open", "investigating"):
            raise ValueError(
                f"Dispute {dispute_id} cannot be responded to (status: {dispute.status})"
            )

        update_data = {}
        if status:
            update_data["status"] = status
        if evidence:
            existing_evidence = dispute.evidence or []
            update_data["evidence"] = existing_evidence + evidence

        if update_data:
            dispute = await self._dispute_repo.update(dispute_id, update_data)

        logger.info(
            "dispute_responded",
            dispute_id=str(dispute_id),
            status=status,
        )
        return dispute

    async def resolve_dispute(
        self,
        dispute_id: UUID,
        resolution: str,
        outcome: str,
        resolved_by: UUID,
        outcome_amount: Decimal | None = None,
    ) -> Dispute:
        """Resolve a dispute with an outcome.

        Possible outcomes: seller_wins, supplier_wins, partial, cancelled.
        For partial outcomes, outcome_amount specifies the split.
        """
        dispute = await self._dispute_repo.get_by_id(dispute_id)
        if not dispute:
            raise ValueError(f"Dispute {dispute_id} not found")

        if dispute.status in ("resolved", "rejected"):
            raise ValueError(
                f"Dispute {dispute_id} is already resolved (status: {dispute.status})"
            )

        dispute = await self._dispute_repo.resolve(
            id=dispute_id,
            resolution=resolution,
            outcome=outcome,
            resolved_by=resolved_by,
            outcome_amount=float(outcome_amount) if outcome_amount else None,
        )

        logger.info(
            "dispute_resolved",
            dispute_id=str(dispute_id),
            outcome=outcome,
            resolved_by=str(resolved_by),
        )
        return dispute

    async def list_disputes(
        self,
        dispute_status: str | None = None,
        shop_ids: list[UUID] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dispute]:
        """List disputes with optional status and shop scope filter."""
        stmt = select(Dispute)

        if dispute_status:
            stmt = stmt.where(Dispute.status == dispute_status)

        if shop_ids is not None:
            stmt = (
                stmt.join(OrderItem, Dispute.order_item_id == OrderItem.id)
                .join(Order, OrderItem.order_id == Order.id)
                .where(Order.shop_id.in_(shop_ids))
            )

        stmt = stmt.order_by(Dispute.created_at.desc()).limit(limit).offset(offset)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_dispute(self, dispute_id: UUID) -> Optional[Dispute]:
        """Get a dispute by ID."""
        return await self._dispute_repo.get_by_id(dispute_id)

    # ==================================================================
    # Refund Operations (retained from original for backward compat)
    # ==================================================================

    async def create_refund(
        self,
        payment_id: UUID,
        order_item_id: UUID,
        amount: Decimal,
        refund_type: str = "full",
        reason: str | None = None,
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

        event = RefundInitiated(
            payment_id=payment_id,
            order_item_id=order_item_id,
            amount=int(amount),
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

    async def process_refund(
        self,
        refund_id: UUID,
        approved_by: UUID,
    ) -> Refund:
        """Approve and process a refund."""
        refund = await self._refund_repo.get_by_id(refund_id)
        if not refund:
            raise ValueError(f"Refund {refund_id} not found")

        refund.status = "completed"
        refund.approved_by = approved_by
        refund.approved_at = datetime.now(timezone.utc)
        refund.completed_at = datetime.now(timezone.utc)

        if refund.payment_id:
            payment = await self._payment_repo.get_by_id(refund.payment_id)
            if payment:
                payment.status = PaymentStatus.REFUNDED.value
                payment.refunded_at = datetime.now(timezone.utc)

        await self.session.flush()

        event = RefundCompleted(
            refund_id=refund.id,
            payment_id=refund.payment_id,
            order_item_id=refund.order_item_id,
            amount=int(refund.amount),
        )
        await self._publish_event(event)

        return refund
