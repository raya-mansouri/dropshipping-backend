"""
Payments API Endpoints
======================
FastAPI endpoints for payment, payout, and dispute management.
All database operations are delegated to PaymentService.
"""

from uuid import UUID
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import (
    get_db,
    get_current_user,
    check_shop_access,
    get_payment_service,
    is_admin,
)
from src.domains.accounts.models import User, Account
from src.domains.shops.models import Shop
from src.domains.payments.schemas import (
    PaymentResponse,
    PaymentStatus,
    SupplierPayoutResponse,
    DisputeResponse,
    DisputeStatus,
)
from src.domains.payments.service import PaymentService


# ============================================
# API Router
# ============================================

router = APIRouter(prefix="/payments", tags=["payments"])


async def _get_user_shop_ids(db: AsyncSession, user: User) -> List[UUID]:
    """Return list of shop IDs owned by the given user."""
    result = await db.execute(
        select(Shop.id)
        .join(Account, Shop.account_id == Account.id)
        .where(Account.owner_user_id == user.id)
    )
    return [row[0] for row in result.all()]


# ---- Payment Endpoints ----


@router.get("/", response_model=List[PaymentResponse])
async def list_payments(
    shop_id: Optional[UUID] = None,
    payment_status: Optional[PaymentStatus] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    svc: PaymentService = Depends(get_payment_service),
):
    """List payments with filters. Scoped to user's shops unless admin."""
    if shop_id:
        await check_shop_access(db, shop_id, current_user)
        return await svc.list_payments(
            payment_status=payment_status,
            shop_ids=[shop_id],
            limit=limit,
            offset=offset,
        )

    if is_admin(current_user):
        return await svc.list_payments(
            payment_status=payment_status,
            limit=limit,
            offset=offset,
        )

    # Non-admin, no shop_id filter: scope to user's shops only
    user_shop_ids = await _get_user_shop_ids(db, current_user)
    if not user_shop_ids:
        return []

    return await svc.list_payments(
        payment_status=payment_status,
        shop_ids=user_shop_ids,
        limit=limit,
        offset=offset,
    )


@router.get("/{payment_id}", response_model=PaymentResponse)
async def get_payment(
    payment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    svc: PaymentService = Depends(get_payment_service),
):
    """Get payment by ID"""
    payment = await svc.get_payment(payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    await check_shop_access(db, payment.order.shop_id, current_user)
    return payment


# ---- Payout Endpoints ----


@router.get("/payouts/", response_model=List[SupplierPayoutResponse])
async def list_payouts(
    supplier_id: Optional[UUID] = None,
    payout_status: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    svc: PaymentService = Depends(get_payment_service),
):
    """List supplier payouts with filters. Scoped to user's shops unless admin."""
    if is_admin(current_user):
        return await svc.list_payouts(
            supplier_id=supplier_id,
            payout_status=payout_status,
            limit=limit,
            offset=offset,
        )

    # Non-admin: scope to user's shops only
    user_shop_ids = await _get_user_shop_ids(db, current_user)
    if not user_shop_ids:
        return []

    # If a specific supplier_id is requested, verify ownership
    if supplier_id and supplier_id not in user_shop_ids:
        raise HTTPException(
            status_code=403,
            detail="You do not have access to this supplier's payouts",
        )

    return await svc.list_payouts(
        supplier_id=supplier_id,
        payout_status=payout_status,
        shop_ids=user_shop_ids,
        limit=limit,
        offset=offset,
    )


@router.get("/payouts/{payout_id}", response_model=SupplierPayoutResponse)
async def get_payout(
    payout_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get payout by ID"""
    from src.domains.payments.repository import SupplierPayoutRepository

    repo = SupplierPayoutRepository(db)
    payout = await repo.get_by_id(payout_id)
    if not payout:
        raise HTTPException(status_code=404, detail="Payout not found")
    return payout


# ---- Dispute Endpoints ----


@router.get("/disputes/", response_model=List[DisputeResponse])
async def list_disputes(
    dispute_status: Optional[DisputeStatus] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    svc: PaymentService = Depends(get_payment_service),
):
    """List disputes with filters. Scoped to user's shops unless admin."""
    if is_admin(current_user):
        return await svc.list_disputes(
            dispute_status=dispute_status.value if dispute_status else None,
            limit=limit,
            offset=offset,
        )

    # Non-admin: scope to user's shops only
    user_shop_ids = await _get_user_shop_ids(db, current_user)
    if not user_shop_ids:
        return []

    return await svc.list_disputes(
        dispute_status=dispute_status.value if dispute_status else None,
        shop_ids=user_shop_ids,
        limit=limit,
        offset=offset,
    )


@router.get("/disputes/{dispute_id}", response_model=DisputeResponse)
async def get_dispute(
    dispute_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    svc: PaymentService = Depends(get_payment_service),
):
    """Get dispute by ID"""
    dispute = await svc.get_dispute(dispute_id)
    if not dispute:
        raise HTTPException(status_code=404, detail="Dispute not found")
    return dispute
