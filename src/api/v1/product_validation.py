"""
Product Validation API Endpoints
================================
FastAPI endpoints for managing forbidden keywords and triggering product scans.
"""

from typing import Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db, get_current_user, require_admin
from src.domains.accounts.models import User
from src.domains.product_validation.schemas import (
    ForbiddenKeywordCreate,
    ForbiddenKeywordResponse,
    ForbiddenKeywordListResponse,
    ProductScanRequest,
    ProductScanResponse,
)
from src.domains.product_validation.service import ProductValidationService

logger = structlog.get_logger(__name__)


# ============================================
# API Router
# ============================================

router = APIRouter(prefix="/product-validation", tags=["product-validation"])


# ---- Keyword CRUD Endpoints ----


@router.get("/keywords", response_model=ForbiddenKeywordListResponse)
async def list_keywords(
    category: Optional[str] = Query(default=None),
    is_active: Optional[bool] = Query(default=True),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """List forbidden keywords with optional filters. Admin only."""
    service = ProductValidationService(db)
    keywords = await service.keyword_filter.list_keywords(
        category=category,
        is_active=is_active,
        limit=limit,
    )
    return ForbiddenKeywordListResponse(
        keywords=keywords,
        total=len(keywords),
    )


@router.post(
    "/keywords",
    response_model=ForbiddenKeywordResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_keyword(
    data: ForbiddenKeywordCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Add a new forbidden keyword. Admin only."""
    service = ProductValidationService(db)
    keyword = await service.keyword_filter.add_keyword(
        keyword=data.keyword,
        category=data.category,
        severity=data.severity,
        language=data.language,
        is_regex=data.is_regex,
        description=data.description or "",
        created_by=current_user.id,
    )
    return keyword


@router.delete("/keywords/{keyword_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_keyword(
    keyword_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Remove (soft-delete) a forbidden keyword. Admin only."""
    service = ProductValidationService(db)
    removed = await service.keyword_filter.remove_keyword(keyword_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Keyword not found")


# ---- Product Scan Endpoint ----


@router.post("/scan/{product_id}", response_model=ProductScanResponse)
async def scan_product(
    product_id: UUID,
    scan_request: ProductScanRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Trigger a keyword scan for a product.

    Scans the product title and description against forbidden keywords
    and returns the validation result.
    """
    service = ProductValidationService(db)
    result = await service.validate_product(
        product_id=product_id,
        title=scan_request.title,
        description=scan_request.description or "",
    )
    return ProductScanResponse(**result)
