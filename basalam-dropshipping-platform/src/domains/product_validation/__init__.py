"""
Product Validation Domain
=========================
Forbidden product detection, keyword scanning, and moderation handling.
"""
from .models import ProductValidationLog, ForbiddenKeyword, ForbiddenProductRule
from .repository import ProductValidationRepository
from .service.keyword_filter import KeywordFilterService
from .service.image_moderation import ImageModerationService
from .schemas import (
    ProductValidationCreate,
    ProductValidationResponse,
    ProductValidationListResponse,
    ForbiddenKeywordCreate,
    ForbiddenKeywordUpdate,
    ForbiddenKeywordResponse,
    ForbiddenKeywordListResponse,
    ProductScanRequest,
    ProductScanResponse,
    ModerationStatusUpdate,
    ModerationStatusResponse,
)

__all__ = [
    "ProductValidationLog",
    "ForbiddenKeyword",
    "ForbiddenProductRule",
    "ProductValidationRepository",
    "KeywordFilterService",
    "ImageModerationService",
    "ProductValidationCreate",
    "ProductValidationResponse",
    "ProductValidationListResponse",
    "ForbiddenKeywordCreate",
    "ForbiddenKeywordUpdate",
    "ForbiddenKeywordResponse",
    "ForbiddenKeywordListResponse",
    "ProductScanRequest",
    "ProductScanResponse",
    "ModerationStatusUpdate",
    "ModerationStatusResponse",
]
