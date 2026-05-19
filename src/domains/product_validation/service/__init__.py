"""
Product Validation Service
==========================
Orchestrates keyword filtering, image moderation, and product validation.

Provides a unified interface for scanning products before they are
listed on seller stores.
"""
import structlog
from typing import Dict, Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ..repository import ProductValidationRepository
from ..models import ProductValidationLog
from .keyword_filter import KeywordFilterService
from .image_moderation import ImageModerationService

logger = structlog.get_logger(__name__)


class ProductValidationService:
    """
    Unified service for product validation.

    Coordinates keyword scanning and image moderation to determine
    if a product is safe for listing.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self._repo = ProductValidationRepository(session)
        self._keyword_filter = KeywordFilterService(session)
        self._image_moderation = ImageModerationService(session)

    async def validate_product(
        self,
        product_id: UUID,
        title: str,
        description: str = "",
    ) -> Dict[str, Any]:
        """
        Run full validation on a product.

        Performs keyword scanning and returns combined results.
        """
        # Keyword scan
        scan_result = await self._keyword_filter.scan_product(title, description)

        # Log the validation
        status = scan_result["status"]
        await self._repo.create({
            "supplier_product_id": product_id,
            "validation_type": "keyword_scan",
            "status": "passed" if scan_result["is_clean"] else "failed",
            "error_message": None if scan_result["is_clean"] else f"Found {len(scan_result['matches'])} forbidden keywords",
            "metadata": scan_result,
        })

        logger.info(
            "product_validated",
            product_id=str(product_id),
            is_clean=scan_result["is_clean"],
            matches=len(scan_result.get("matches", [])),
        )

        return scan_result

    async def handle_moderation_status(
        self,
        product_id: UUID,
        moderation_status: str,
        reason: Optional[str] = None,
        rejected_images: Optional[list] = None,
    ):
        """Delegate to image moderation service."""
        return await self._image_moderation.handle_moderation_status(
            product_id=product_id,
            moderation_status=moderation_status,
            reason=reason,
            rejected_images=rejected_images,
        )

    # Expose keyword CRUD for admin endpoints
    @property
    def keyword_filter(self) -> KeywordFilterService:
        return self._keyword_filter

    @property
    def image_moderation(self) -> ImageModerationService:
        return self._image_moderation
