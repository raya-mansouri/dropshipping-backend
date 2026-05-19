"""
Pricing API Endpoints
=====================
FastAPI endpoints for price calculation, validation, and history
"""

from uuid import UUID
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.deps import get_db, get_current_user, get_pricing_service
from src.domains.accounts.models import User
from src.domains.pricing.schemas import (
    PriceCalculateRequest,
    PriceCalculateResponse,
    PriceValidationRequest,
    PriceValidationResponse,
    PriceHistoryResponse,
)
from src.domains.pricing.service import PricingService


# ============================================
# API Router
# ============================================

router = APIRouter(prefix="/pricing", tags=["pricing"])


# ---- Pricing Endpoints ----


@router.post("/calculate", response_model=PriceCalculateResponse)
async def calculate_price(
    body: PriceCalculateRequest,
    pricing_service: PricingService = Depends(get_pricing_service),
    current_user: User = Depends(get_current_user),
):
    """Calculate seller price from supplier price and margin."""
    result = await pricing_service.calculate_price(
        supplier_price=body.supplier_price,
        margin_percent=body.margin_percent,
        category_id=body.category_id,
    )
    return PriceCalculateResponse(
        supplier_price=result.supplier_price,
        margin_percent=result.margin_percent,
        seller_price=result.seller_price,
        profit=result.profit,
        category_franchise_percent=result.category_franchise_percent,
        meets_franchise_requirement=result.meets_franchise_requirement,
    )


@router.post("/validate", response_model=PriceValidationResponse)
async def validate_price(
    body: PriceValidationRequest,
    pricing_service: PricingService = Depends(get_pricing_service),
    current_user: User = Depends(get_current_user),
):
    """Validate price against category franchise rules."""
    result = await pricing_service.validate_price(
        seller_price=body.seller_price,
        supplier_price=body.supplier_price,
        category_id=body.category_id,
    )
    return PriceValidationResponse(
        is_valid=result.is_valid,
        margin_percent=result.margin_percent,
        category_franchise_percent=result.category_franchise_percent,
        validation_errors=result.validation_errors,
    )


@router.get("/history/{variant_id}", response_model=List[PriceHistoryResponse])
async def get_price_history(
    variant_id: UUID,
    limit: int = 50,
    pricing_service: PricingService = Depends(get_pricing_service),
    current_user: User = Depends(get_current_user),
):
    """Get price history for a variant."""
    records = await pricing_service.get_price_history(
        variant_id=variant_id,
        limit=limit,
    )
    return records
