"""
Image Moderation Service
========================
Handles product image moderation status from Basalam.

When Basalam moderation flags images:
- pending_review: Disable seller products, notify sellers
- approved: Re-enable seller products, notify sellers
- rejected: Mark images as rejected, disable affected products
"""
import structlog
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.products.models import SupplierProduct, ProductMedia

logger = structlog.get_logger(__name__)


class ImageModerationService:
    """
    Service for handling image moderation from Basalam.

    Processes moderation status changes and cascades
    to seller listings and notifications.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def handle_moderation_status(
        self,
        product_id: UUID,
        moderation_status: str,
        reason: Optional[str] = None,
        rejected_images: Optional[List[UUID]] = None,
    ) -> Optional[SupplierProduct]:
        """
        Handle moderation status change from Basalam.

        Args:
            product_id: UUID of the supplier product
            moderation_status: New moderation status (pending_review, approved, rejected)
            reason: Reason for rejection
            rejected_images: List of rejected image UUIDs

        Returns:
            Updated SupplierProduct or None
        """
        result = await self.session.execute(
            select(SupplierProduct).where(SupplierProduct.id == product_id)
        )
        product = result.scalar_one_or_none()

        if not product:
            logger.warning("product_not_found_for_moderation", product_id=str(product_id))
            return None

        old_status = product.moderation_status
        product.moderation_status = moderation_status

        if moderation_status == "pending_review":
            # Keep product active during grace period (24h per spec)
            # but flag for review
            product.basalam_validation_error = {
                "moderation_status": "pending_review",
                "reason": reason,
                "flagged_at": datetime.now(timezone.utc).isoformat(),
            }

            logger.info(
                "product_flagged_for_review",
                product_id=str(product_id),
                old_status=old_status,
            )

        elif moderation_status == "approved":
            # Clear any previous validation errors
            product.basalam_validation_error = None
            # Make sure product is active if it was disabled for review
            if product.status == "pending_review":
                product.status = "active"

            logger.info(
                "product_approved_by_moderation",
                product_id=str(product_id),
            )

        elif moderation_status == "rejected":
            product.status = "forbidden"
            product.basalam_validation_error = {
                "moderation_status": "rejected",
                "reason": reason or "Image/content rejected by Basalam moderation",
                "rejected_images": [str(img_id) for img_id in (rejected_images or [])],
                "rejected_at": datetime.now(timezone.utc).isoformat(),
            }

            # Mark specific images as rejected
            if rejected_images:
                await self.session.execute(
                    update(ProductMedia)
                    .where(ProductMedia.id.in_(rejected_images))
                    .values(status="rejected")
                )

            logger.warning(
                "product_rejected_by_moderation",
                product_id=str(product_id),
                reason=reason,
            )

        await self.session.flush()
        return product

    async def get_products_pending_review(
        self,
        limit: int = 50,
    ) -> List[SupplierProduct]:
        """Get products currently in pending_review status."""
        result = await self.session.execute(
            select(SupplierProduct)
            .where(SupplierProduct.moderation_status == "pending_review")
            .order_by(SupplierProduct.updated_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_rejected_images(
        self,
        product_id: UUID,
    ) -> List[ProductMedia]:
        """Get all rejected images for a product."""
        result = await self.session.execute(
            select(ProductMedia)
            .where(
                ProductMedia.product_id == product_id,
                ProductMedia.status == "rejected",
            )
        )
        return list(result.scalars().all())

    async def recheck_product_images(
        self,
        product_id: UUID,
    ) -> Dict[str, Any]:
        """
        Recheck a product's images after supplier updates them.

        Returns a summary of image statuses.
        """
        result = await self.session.execute(
            select(ProductMedia)
            .where(ProductMedia.product_id == product_id)
            .order_by(ProductMedia.sort_order)
        )
        images = list(result.scalars().all())

        status_counts = {}
        for img in images:
            status_counts[img.status] = status_counts.get(img.status, 0) + 1

        all_approved = all(img.status in ("processed", "pending") for img in images)

        return {
            "product_id": str(product_id),
            "total_images": len(images),
            "status_counts": status_counts,
            "all_approved": all_approved,
        }
