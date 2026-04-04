"""
Order Sync Celery Tasks
=======================
Periodic order synchronization tasks.
"""
import asyncio
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


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
    logger.info("Starting order sync task")
    try:
        async def _sync():
            from src.core.database import async_session_maker
            from src.domains.orders.models import Order
            from src.domains.payments.service import PaymentService
            from sqlalchemy import select

            async with async_session_maker() as session:
                # Find delivered orders with pending payouts
                payout_stmt = (
                    select(Order)
                    .where(Order.status.in_(["delivered", "completed"]))
                    .limit(100)
                )
                await session.execute(payout_stmt)

                payment_service = PaymentService(session)
                released = await payment_service.release_mature_payouts()
                logger.info(f"Released {len(released)} payouts during order sync")

        asyncio.run(_sync())
        logger.info("Order sync task completed")
    except Exception as exc:
        logger.error(f"Order sync task failed: {exc}")
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
    logger.info("Starting auto-confirm deliveries task")
    try:
        async def _confirm():
            from src.core.database import async_session_maker
            from src.domains.payments.service import PaymentService

            async with async_session_maker() as session:
                # Release payouts where dispute window has expired
                payment_service = PaymentService(session)
                released = await payment_service.release_mature_payouts()

                for payout in released:
                    logger.info(f"Auto-released payout {payout.id} for supplier {payout.supplier_id}")

                await session.commit()

        asyncio.run(_confirm())
        logger.info("Auto-confirm deliveries task completed")
    except Exception as exc:
        logger.error(f"Auto-confirm deliveries task failed: {exc}")
        raise self.retry(exc=exc)
