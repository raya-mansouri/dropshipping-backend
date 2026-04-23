"""
Payment Gateway & Wallet API Endpoints
=======================================
FastAPI endpoints for wallet deposits, gateway callbacks, balance queries,
and order payments via wallet.
"""

import structlog
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db, get_current_user, get_payment_service
from src.core.config import get_settings
from src.domains.accounts.models import User
from src.domains.payments.schemas import (
    WalletDepositRequest,
    WalletDepositResponse,
    WalletBalanceResponse,
    PayOrderResponse,
)
from src.domains.payments.service import PaymentService
from src.integrations.payment.factory import PaymentProviderFactory

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/payment", tags=["payment"])


# ---- Wallet Deposit ----


@router.post("/deposit", response_model=WalletDepositResponse)
async def initiate_wallet_deposit(
    body: WalletDepositRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    svc: PaymentService = Depends(get_payment_service),
):
    """Initiate a wallet deposit via Zarinpal payment gateway.

    Returns a payment URL to redirect the user to.
    """
    settings = get_settings()
    callback_url = settings.payment_callback_url
    if not callback_url:
        callback_url = f"{settings.base_url}/api/v1/payment/callback"

    try:
        provider = PaymentProviderFactory.get_provider()
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))

    result = await provider.create_payment(
        amount=body.amount,
        callback_url=callback_url,
        description=f"شارژ کیف پول - کاربر {current_user.phone}",
        metadata={"user_id": str(current_user.id), "phone": current_user.phone},
    )

    if not result.get("status"):
        raise HTTPException(
            status_code=502,
            detail=result.get("message", "Failed to create payment"),
        )

    # Create pending wallet transaction
    tx = await svc.create_deposit_transaction(
        user_id=current_user.id,
        amount=body.amount,
        token=result["token"],
        gateway=settings.payment_gateway,
    )
    await db.commit()

    logger.info(
        "wallet_deposit_initiated",
        user_id=str(current_user.id),
        amount=body.amount,
        token=result["token"],
    )

    return WalletDepositResponse(
        transaction_id=tx.id,
        payment_url=result["url"],
    )


# ---- Gateway Callback ----


@router.post("/callback")
@router.get("/callback")
async def payment_gateway_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle payment gateway callback (verification).

    For Zarinpal, the gateway sends Authority and Status as query parameters.
    """
    # Extract params from query string (Zarinpal sends GET callback)
    params = dict(request.query_params)
    authority = params.get("Authority", "")
    gateway_status = params.get("Status", "")

    if not authority:
        raise HTTPException(status_code=400, detail="Missing Authority parameter")

    # Handle user cancellation
    if gateway_status != "OK":
        svc = PaymentService(db, event_publisher=None)
        await svc.fail_deposit(authority)
        await db.commit()
        logger.info("payment_cancelled_by_user", authority=authority)
        return {"status": "cancelled", "message": "Payment was cancelled by user"}

    # Find the pending transaction
    from sqlalchemy import select, and_
    from src.domains.payments.models import (
        WalletTransaction,
        TransactionType,
        TransactionStatus,
    )

    stmt = select(WalletTransaction).where(
        and_(
            WalletTransaction.reference_id == authority,
            WalletTransaction.reference_type == "payment",
            WalletTransaction.type == TransactionType.DEPOSIT.value,
            WalletTransaction.status == TransactionStatus.PENDING.value,
        )
    )
    result = await db.execute(stmt)
    tx = result.scalar_one_or_none()

    if not tx:
        # Anti-replay: check if already completed (duplicate callback from gateway)
        completed_stmt = select(WalletTransaction).where(
            and_(
                WalletTransaction.reference_id == authority,
                WalletTransaction.reference_type == "payment",
                WalletTransaction.type == TransactionType.DEPOSIT.value,
                WalletTransaction.status == TransactionStatus.COMPLETED.value,
            )
        )
        completed_result = await db.execute(completed_stmt)
        completed_tx = completed_result.scalar_one_or_none()

        if completed_tx:
            logger.info(
                "payment_callback_duplicate",
                authority=authority,
                transaction_id=str(completed_tx.id),
            )
            return {
                "status": "success",
                "ref_id": completed_tx.gateway_ref_id,
                "amount": int(completed_tx.amount),
            }

        raise HTTPException(status_code=404, detail="Transaction not found")

    # Verify with gateway
    try:
        provider = PaymentProviderFactory.get_provider()
        verify_result = await provider.verify_payment(
            token=authority,
            amount=tx.amount,
        )
    except Exception as e:
        logger.error("gateway_verification_failed", authority=authority, error=str(e))
        raise HTTPException(status_code=502, detail="Gateway verification failed")

    svc = PaymentService(
        db, event_publisher=getattr(request.app.state, "event_publisher", None)
    )

    if verify_result.get("status"):
        await svc.verify_and_complete_deposit(
            token=authority,
            user_id=tx.user_id,
            gateway_ref_id=str(verify_result.get("ref_id", "")),
            extra_metadata={"gateway_response": verify_result},
        )
        await db.commit()

        logger.info(
            "wallet_deposit_verified",
            authority=authority,
            ref_id=verify_result.get("ref_id"),
            amount=str(tx.amount),
        )
        return {
            "status": "success",
            "ref_id": verify_result.get("ref_id"),
            "amount": int(tx.amount),
        }
    else:
        await svc.fail_deposit(authority)
        await db.commit()

        logger.warning(
            "wallet_deposit_verification_failed",
            authority=authority,
            code=verify_result.get("code"),
            message=verify_result.get("message"),
        )
        raise HTTPException(
            status_code=400,
            detail=verify_result.get("message", "Payment verification failed"),
        )


# ---- Wallet Balance ----


@router.get("/wallet", response_model=WalletBalanceResponse)
async def get_wallet_balance(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    svc: PaymentService = Depends(get_payment_service),
):
    """Get current user's wallet balance and pending amount."""
    balance = await svc.get_wallet_balance(current_user.id)
    pending = await svc.get_pending_amount(current_user.id)

    return WalletBalanceResponse(
        user_id=current_user.id,
        balance=balance,
        pending_amount=pending,
    )


# ---- Pay Order from Wallet ----


@router.post("/pay-order/{order_id}", response_model=PayOrderResponse)
async def pay_order_from_wallet(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    svc: PaymentService = Depends(get_payment_service),
):
    """Pay for an order from wallet balance.

    Uses atomic row locking to prevent double-payment.
    Deducts items cost + shipping + commission from wallet.
    """
    try:
        payment = await svc.pay_order_from_wallet(
            order_id=order_id,
            user_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    await db.commit()

    total_paid = (
        int(payment.seller_paid_amount)
        + int(payment.shipping_cost)
        + int(payment.platform_fee)
    )

    logger.info(
        "order_paid_from_wallet",
        order_id=str(order_id),
        payment_id=str(payment.id),
        user_id=str(current_user.id),
        total_paid=total_paid,
    )

    return PayOrderResponse(
        payment_id=payment.id,
        order_id=order_id,
        total_paid=total_paid,
        breakdown={
            "items": int(payment.seller_paid_amount),
            "shipping": int(payment.shipping_cost),
            "commission": int(payment.platform_fee),
        },
    )
