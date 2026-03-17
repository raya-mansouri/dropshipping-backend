import asyncio
import logging
import uuid
from datetime import datetime
from typing import List

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import AsyncSessionLocal
from src.domains.inventory.models import InventoryReservation
from src.domains.inventory.repository import (
    InventoryReservationRepository,
)
from src.domains.inventory.service.reservation_service import ReservationService
from src.domains.inventory.service.sync_service import InventorySyncService
from src.domains.shops.repository import ShopIntegrationRepository

logger = logging.getLogger(__name__)


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


async def notify_sellers(reservations: List[InventoryReservation]) -> None:
    from src.integrations.notification.manager import NotificationManager

    seller_ids = set()
    for reservation in reservations:
        if reservation.order_item and reservation.order_item.order:
            seller_ids.add(reservation.order_item.order.seller_id)

    if not seller_ids:
        return

    notification_manager = NotificationManager()
    for seller_id in seller_ids:
        try:
            await notification_manager.send_notification(
                recipient_id=seller_id,
                notification_type="inventory_expired",
                title="Inventory Reservation Expired",
                body=f"{len(reservations)} reservation(s) have expired due to payment timeout.",
                metadata={"reservation_count": len(reservations)},
            )
        except Exception as e:
            logger.error(f"Failed to notify seller {seller_id}: {e}")


@shared_task(bind=True, max_retries=3)
def cleanup_expired_reservations(self):
    logger.info("Starting cleanup of expired inventory reservations")

    async def _cleanup():
        async with AsyncSessionLocal() as session:
            reservation_repo = InventoryReservationRepository(session)
            expired_reservations = await reservation_repo.get_expired()

            if not expired_reservations:
                logger.info("No expired reservations found")
                return {"processed": 0, "released": 0}

            processed = 0
            released = 0

            for reservation in expired_reservations:
                try:
                    reservation_service = ReservationService(session)
                    await reservation_service.release_inventory(
                        order_item_id=reservation.order_item_id,
                        reason="payment_timeout",
                    )
                    released += 1
                except Exception as e:
                    logger.error(f"Failed to release reservation {reservation.id}: {e}")
                finally:
                    processed += 1

            await session.commit()

            if released > 0:
                try:
                    await notify_sellers(expired_reservations)
                except Exception as e:
                    logger.error(f"Failed to notify sellers: {e}")

            logger.info(
                f"Cleanup completed: {processed} processed, {released} released"
            )
            return {"processed": processed, "released": released}

    result = asyncio.run(_cleanup())
    return result


@shared_task(bind=True, max_retries=3)
def reconcile_inventory(self, integration_id: str = None):
    logger.info(f"Starting inventory reconciliation for integration {integration_id}")

    async def _reconcile():
        from src.domains.shops.models import ShopIntegration

        async with AsyncSessionLocal() as session:
            if integration_id:
                integration_ids = [uuid.UUID(integration_id)]
            else:
                result = await session.execute(
                    select(ShopIntegration).where(ShopIntegration.status == "active")
                )
                integrations = result.scalars().all()
                integration_ids = [i.id for i in integrations]

            results = []
            for int_id in integration_ids:
                try:
                    sync_service = InventorySyncService(session)
                    result = await sync_service.reconcile(int_id)
                    await session.commit()

                    logger.info(
                        f"Reconciliation completed for {int_id}: {result.total_variants} variants, "
                        f"{result.matched_count} matched, {result.mismatch_count} mismatches, "
                        f"{result.fixed_count} fixed"
                    )

                    results.append(
                        {
                            "integration_id": str(int_id),
                            "success": result.success,
                            "total_variants": result.total_variants,
                            "matched_count": result.matched_count,
                            "mismatch_count": result.mismatch_count,
                            "fixed_count": result.fixed_count,
                            "errors": result.errors,
                        }
                    )
                except Exception as e:
                    logger.error(f"Reconciliation failed for {int_id}: {e}")
                    results.append(
                        {
                            "integration_id": str(int_id),
                            "success": False,
                            "error": str(e),
                        }
                    )

            return results


@shared_task(bind=True, max_retries=3)
def sync_inventory(self, integration_id: str = None):
    logger.info(f"Starting inventory sync for integration {integration_id}")

    async def _sync():
        from src.domains.shops.models import ShopIntegration

        async with AsyncSessionLocal() as session:
            if integration_id:
                integration_ids = [uuid.UUID(integration_id)]
            else:
                result = await session.execute(
                    select(ShopIntegration).where(ShopIntegration.status == "active")
                )
                integrations = result.scalars().all()
                integration_ids = [i.id for i in integrations]

            results = []
            for int_id in integration_ids:
                try:
                    integration_repo = ShopIntegrationRepository(session)
                    integration = await integration_repo.get_by_id(int_id)

                    if not integration:
                        logger.error(f"Integration {int_id} not found")
                        continue

                    sync_service = InventorySyncService(session)
                    result = await sync_service.sync_from_supplier(int_id)
                    await session.commit()

                    if result.success:
                        await integration_repo.update(
                            int_id,
                            {"last_sync_at": datetime.utcnow()},
                        )
                        await session.commit()

                    logger.info(
                        f"Sync completed for {int_id}: {result.variants_updated}/{result.total_variants} "
                        f"variants updated"
                    )

                    results.append(
                        {
                            "integration_id": str(int_id),
                            "success": result.success,
                            "variants_updated": result.variants_updated,
                            "total_variants": result.total_variants,
                            "errors": result.errors,
                        }
                    )
                except Exception as e:
                    logger.error(f"Sync failed for {int_id}: {e}")
                    results.append(
                        {
                            "integration_id": str(int_id),
                            "success": False,
                            "error": str(e),
                        }
                    )

            return results

    result = asyncio.run(_sync())
    return result
