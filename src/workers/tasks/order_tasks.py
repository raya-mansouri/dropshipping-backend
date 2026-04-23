"""
Order Sync Celery Tasks
=======================
Periodic order synchronization and auto-confirm delivery tasks.
"""

import structlog

from celery import shared_task

from src.workers.celery_config import run_async

logger = structlog.get_logger(__name__)


@shared_task(
    bind=True,
    name="src.workers.tasks.order_tasks.order_sync",
    max_retries=3,
    default_retry_delay=120,
    retry_jitter=True,
    acks_late=True,
)
def order_sync(self):
    """Sync orders with Basalam for all active integrations."""
    logger.info("starting_order_sync_task")
    try:

        async def _sync():
            from datetime import datetime, timezone
            from decimal import Decimal

            from sqlalchemy import select

            from src.core.config import get_settings
            from src.core.database import async_session_maker
            from src.core.events.publisher import EventPublisher
            from src.core.events.order import OrderCreated, OrderStatusChanged
            from src.domains.orders.models import (
                Order,
                OrderItem,
                OrderStatus,
                OrderHistory,
            )
            from src.domains.products.models import ProductVariant
            from src.domains.shops.models import ShopIntegration, Platform
            from src.integrations.basalam.client import BasalamClient

            settings = get_settings()
            publisher = EventPublisher(
                kafka_bootstrap_servers=settings.kafka_bootstrap_servers,
            )

            try:
                async with async_session_maker() as session:
                    # Fetch active Basalam integrations joined with platform
                    stmt = (
                        select(ShopIntegration)
                        .join(Platform, Platform.id == ShopIntegration.platform_id)
                        .where(
                            ShopIntegration.status == "connected",
                            Platform.code == "basalam",
                        )
                    )
                    result = await session.execute(stmt)
                    integrations = result.scalars().all()

                    if not integrations:
                        logger.info("order_sync_no_active_integrations")
                        return

                    total_created = 0
                    total_updated = 0

                    for integration in integrations:
                        try:
                            credentials = integration.credentials or {}
                            client = BasalamClient(
                                client_id=credentials.get("client_id", ""),
                                client_secret=credentials.get("client_secret", ""),
                                access_token=credentials.get("access_token"),
                                refresh_token=credentials.get("refresh_token"),
                            )
                            try:
                                # Fetch recent orders from Basalam
                                basalam_orders_resp = await client.list_orders(page=1)
                                basalam_orders = basalam_orders_resp.get("orders", [])

                                for basalam_order in basalam_orders:
                                    try:
                                        external_id = basalam_order.get("id")
                                        if not external_id:
                                            continue

                                        basalam_status = basalam_order.get(
                                            "status", "PENDING"
                                        ).lower()
                                        # Map Basalam status to our internal enum values
                                        status_map = {
                                            "pending": OrderStatus.PENDING,
                                            "confirmed": OrderStatus.CONFIRMED,
                                            "processing": OrderStatus.PROCESSING,
                                            "shipped": OrderStatus.SHIPPED,
                                            "delivered": OrderStatus.DELIVERED,
                                            "cancelled": OrderStatus.CANCELLED,
                                        }
                                        mapped_status = status_map.get(
                                            basalam_status, OrderStatus.PENDING
                                        )

                                        # Check if order already exists
                                        existing_stmt = select(Order).where(
                                            Order.external_order_id == str(external_id),
                                            Order.shop_id == integration.shop_id,
                                        )
                                        existing_result = await session.execute(
                                            existing_stmt
                                        )
                                        existing_order = (
                                            existing_result.scalar_one_or_none()
                                        )

                                        if existing_order is None:
                                            # Create new order
                                            order_items = basalam_order.get("items", [])
                                            total = basalam_order.get("total", 0)
                                            shipping_cost = basalam_order.get(
                                                "shipping_cost", 0
                                            )

                                            new_order = Order(
                                                shop_id=integration.shop_id,
                                                external_order_id=str(external_id),
                                                customer_data=basalam_order.get(
                                                    "customer", {}
                                                ),
                                                total_price=Decimal(str(total)),
                                                shipping_price=Decimal(
                                                    str(shipping_cost)
                                                ),
                                                discount=Decimal("0"),
                                                status=mapped_status.value,
                                                notes=basalam_order.get("notes"),
                                                extra_data={
                                                    "basalam_order_number": basalam_order.get(
                                                        "order_number"
                                                    ),
                                                    "synced_at": datetime.now(
                                                        timezone.utc
                                                    ).isoformat(),
                                                },
                                                created_at=datetime.now(timezone.utc),
                                                updated_at=datetime.now(timezone.utc),
                                            )
                                            session.add(new_order)
                                            await session.flush()

                                            # Create order items
                                            for item_data in order_items:
                                                # Look up variant by external ID
                                                external_variant_id = (
                                                    str(item_data.get("variant_id", ""))
                                                    if item_data.get("variant_id")
                                                    else None
                                                )

                                                variant_id = None
                                                if external_variant_id:
                                                    variant_stmt = select(
                                                        ProductVariant
                                                    ).where(
                                                        ProductVariant.external_variant_id
                                                        == external_variant_id,
                                                    )
                                                    variant_result = (
                                                        await session.execute(
                                                            variant_stmt
                                                        )
                                                    )
                                                    variant = variant_result.scalar_one_or_none()
                                                    if variant:
                                                        variant_id = variant.id

                                                if not variant_id:
                                                    logger.warning(
                                                        "order_sync_variant_not_found",
                                                        external_variant_id=str(
                                                            external_variant_id
                                                        ),
                                                        external_order_id=str(
                                                            external_id
                                                        ),
                                                    )
                                                    continue

                                                order_item = OrderItem(
                                                    order_id=new_order.id,
                                                    supplier_shop_id=integration.shop_id,
                                                    variant_id=variant_id,
                                                    quantity=item_data.get(
                                                        "quantity", 1
                                                    ),
                                                    supplier_price=Decimal(
                                                        str(item_data.get("price", 0))
                                                    ),
                                                    seller_price=Decimal(
                                                        str(
                                                            item_data.get(
                                                                "total_price", 0
                                                            )
                                                        )
                                                    ),
                                                    shipping_price=Decimal("0"),
                                                    profit=Decimal("0"),
                                                    status=mapped_status.value,
                                                    created_at=datetime.now(
                                                        timezone.utc
                                                    ),
                                                    updated_at=datetime.now(
                                                        timezone.utc
                                                    ),
                                                )
                                                session.add(order_item)

                                            await session.flush()

                                            # Publish OrderCreated event
                                            event = OrderCreated(
                                                order_id=new_order.id,
                                                shop_id=integration.shop_id,
                                                total_price=int(total),
                                                items_count=len(order_items),
                                            )
                                            await publisher.publish(
                                                topic="events", event=event
                                            )

                                            total_created += 1
                                            logger.info(
                                                "order_sync_created",
                                                order_id=str(new_order.id),
                                                external_order_id=str(external_id),
                                                integration_id=str(integration.id),
                                            )
                                        else:
                                            # Sync status changes from Basalam
                                            current_status = OrderStatus(
                                                existing_order.status
                                            )
                                            if current_status != mapped_status:
                                                old_status_val = existing_order.status
                                                existing_order.status = (
                                                    mapped_status.value
                                                )
                                                existing_order.updated_at = (
                                                    datetime.now(timezone.utc)
                                                )

                                                # Update timestamp fields
                                                timestamp_field = {
                                                    OrderStatus.CONFIRMED: "confirmed_at",
                                                    OrderStatus.PAID: "paid_at",
                                                    OrderStatus.SHIPPED: "shipped_at",
                                                    OrderStatus.DELIVERED: "delivered_at",
                                                    OrderStatus.COMPLETED: "completed_at",
                                                    OrderStatus.CANCELLED: "cancelled_at",
                                                }.get(mapped_status)

                                                if timestamp_field:
                                                    setattr(
                                                        existing_order,
                                                        timestamp_field,
                                                        datetime.now(timezone.utc),
                                                    )

                                                # Record history
                                                history = OrderHistory(
                                                    order_id=existing_order.id,
                                                    from_status=old_status_val,
                                                    to_status=mapped_status.value,
                                                    actor_type="system",
                                                    reason="basalam_sync",
                                                    created_at=datetime.now(
                                                        timezone.utc
                                                    ),
                                                )
                                                session.add(history)

                                                # Publish OrderStatusChanged event
                                                status_event = OrderStatusChanged(
                                                    order_id=existing_order.id,
                                                    old_status=old_status_val,
                                                    new_status=mapped_status.value,
                                                    actor="system",
                                                )
                                                await publisher.publish(
                                                    topic="events", event=status_event
                                                )

                                                total_updated += 1
                                                logger.info(
                                                    "order_sync_updated",
                                                    order_id=str(existing_order.id),
                                                    external_order_id=str(external_id),
                                                    old_status=old_status_val,
                                                    new_status=mapped_status.value,
                                                )

                                    except Exception as item_err:
                                        logger.error(
                                            "order_sync_item_failed",
                                            external_order_id=str(
                                                basalam_order.get("id")
                                            ),
                                            integration_id=str(integration.id),
                                            error=str(item_err),
                                        )

                            finally:
                                await client.close()

                            logger.info(
                                "order_sync_integration_completed",
                                integration_id=str(integration.id),
                            )
                        except Exception as int_err:
                            logger.error(
                                "order_sync_integration_failed",
                                integration_id=str(integration.id),
                                error=str(int_err),
                            )

                    await session.commit()

                    logger.info(
                        "order_sync_task_completed",
                        integrations=len(integrations),
                        total_created=total_created,
                        total_updated=total_updated,
                    )
            finally:
                await publisher.close()

        run_async(_sync())
    except Exception as exc:
        logger.error("order_sync_task_failed", error=str(exc))
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    name="src.workers.tasks.order_tasks.auto_confirm_deliveries",
    max_retries=2,
    retry_jitter=True,
    acks_late=True,
)
def auto_confirm_deliveries(self):
    """Auto-confirm deliveries after dispute window expires (72h normal / 7d high-value)."""
    logger.info("starting_auto_confirm_deliveries_task")
    try:

        async def _confirm():
            from datetime import datetime, timedelta, timezone

            from sqlalchemy import select, and_

            from src.core.config import get_settings
            from src.core.database import async_session_maker
            from src.core.events.publisher import EventPublisher
            from src.core.events.order import OrderStatusChanged
            from src.core.events.payment import PaymentReleasedToSupplier
            from src.domains.orders.models import (
                Order,
                OrderItem,
                OrderStatus,
                OrderHistory,
            )
            from src.domains.payments.models import Payment, SupplierPayout
            from src.domains.payments.service import (
                NORMAL_DISPUTE_WINDOW_HOURS,
                HIGH_VALUE_DISPUTE_WINDOW_DAYS,
                HIGH_VALUE_THRESHOLD,
            )

            settings = get_settings()
            publisher = EventPublisher(
                kafka_bootstrap_servers=settings.kafka_bootstrap_servers,
            )

            try:
                async with async_session_maker() as session:
                    # Dispute window: use normal (72h) window for eligibility cutoff;
                    # per-item high-value (7d) dispute_hours is still applied below
                    # when creating SupplierPayout records.
                    dispute_window = timedelta(hours=NORMAL_DISPUTE_WINDOW_HOURS)
                    cutoff = datetime.now(timezone.utc) - dispute_window

                    # Query delivered orders past the dispute window
                    stmt = (
                        select(Order)
                        .where(
                            and_(
                                Order.status == OrderStatus.DELIVERED.value,
                                Order.delivered_at <= cutoff,
                            )
                        )
                        .limit(500)
                    )
                    result = await session.execute(stmt)
                    eligible_orders = result.scalars().all()

                    if not eligible_orders:
                        logger.info("auto_confirm_no_eligible_orders")
                        return

                    completed_count = 0
                    payouts_created = 0

                    for order in eligible_orders:
                        try:
                            now = datetime.now(timezone.utc)

                            # Transition order to completed
                            old_status = order.status
                            order.status = OrderStatus.COMPLETED.value
                            order.completed_at = now
                            order.updated_at = now

                            # Record history
                            history = OrderHistory(
                                order_id=order.id,
                                from_status=old_status,
                                to_status=OrderStatus.COMPLETED.value,
                                actor_type="system",
                                reason="auto_confirm_dispute_window_expired",
                                created_at=now,
                            )
                            session.add(history)

                            # Publish OrderStatusChanged event
                            status_event = OrderStatusChanged(
                                order_id=order.id,
                                old_status=old_status,
                                new_status=OrderStatus.COMPLETED.value,
                                actor="system",
                            )
                            await publisher.publish(topic="events", event=status_event)

                            # Fetch order items and payments for escrow release
                            items_stmt = select(OrderItem).where(
                                OrderItem.order_id == order.id
                            )
                            items_result = await session.execute(items_stmt)
                            order_items = items_result.scalars().all()

                            payment_stmt = select(Payment).where(
                                Payment.order_id == order.id
                            )
                            payment_result = await session.execute(payment_stmt)
                            payment = payment_result.scalar_one_or_none()

                            for item in order_items:
                                try:
                                    if not payment:
                                        logger.warning(
                                            "auto_confirm_no_payment_found",
                                            order_id=str(order.id),
                                            order_item_id=str(item.id),
                                        )
                                        continue

                                    # Determine dispute window for this item
                                    is_high_value = (
                                        item.seller_price * item.quantity
                                        >= HIGH_VALUE_THRESHOLD
                                    )
                                    dispute_hours = (
                                        HIGH_VALUE_DISPUTE_WINDOW_DAYS * 24
                                        if is_high_value
                                        else NORMAL_DISPUTE_WINDOW_HOURS
                                    )

                                    supplier_amount = (
                                        item.supplier_price * item.quantity
                                    )

                                    # Create SupplierPayout record
                                    payout = SupplierPayout(
                                        supplier_id=item.supplier_shop_id,
                                        order_item_id=item.id,
                                        payment_id=payment.id,
                                        amount=supplier_amount,
                                        status="completed",
                                        release_conditions_met=True,
                                        delivery_confirmed_at=order.delivered_at,
                                        dispute_window_ends_at=(
                                            order.delivered_at
                                            + timedelta(hours=dispute_hours)
                                        ),
                                        released_at=now,
                                    )
                                    session.add(payout)
                                    payouts_created += 1

                                    # Publish PaymentReleasedToSupplier event
                                    release_event = PaymentReleasedToSupplier(
                                        order_id=order.id,
                                        payment_id=payment.id,
                                        supplier_id=item.supplier_shop_id,
                                        amount=int(supplier_amount),
                                    )
                                    await publisher.publish(
                                        topic="events", event=release_event
                                    )

                                except Exception as payout_err:
                                    logger.error(
                                        "auto_confirm_payout_failed",
                                        order_id=str(order.id),
                                        order_item_id=str(item.id),
                                        error=str(payout_err),
                                    )

                            # Update payment status to supplier_paid
                            if payment:
                                payment.status = "supplier_paid"
                                payment.supplier_paid_at = now

                            completed_count += 1
                            logger.info(
                                "auto_confirmed_order",
                                order_id=str(order.id),
                                items_count=len(order_items),
                            )

                        except Exception as order_err:
                            logger.error(
                                "auto_confirm_order_failed",
                                order_id=str(order.id),
                                error=str(order_err),
                            )

                    await session.commit()

                    logger.info(
                        "auto_confirm_deliveries_completed",
                        completed=completed_count,
                        payouts_created=payouts_created,
                    )
            finally:
                await publisher.close()

        run_async(_confirm())
    except Exception as exc:
        logger.error("auto_confirm_deliveries_task_failed", error=str(exc))
        raise self.retry(exc=exc)
