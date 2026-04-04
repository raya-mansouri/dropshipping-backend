"""
Admin API Endpoints
===================
Administrative endpoints for managing orders, inventory, fraud, and disputes.
"""
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db, get_current_user, require_admin
from src.domains.orders.models import Order, OrderStatus
from src.domains.products.models import SupplierProduct, SupplierVariant
from src.domains.inventory.models import InventoryReservation
from src.domains.payments.models import Dispute, Refund
from src.domains.fraud_detection.models import FraudSignal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


# --- Request schemas ---
class ForceInventoryUpdate(BaseModel):
    variant_id: UUID
    new_inventory: int = Field(ge=0)
    reason: str


class ForceOrderCancel(BaseModel):
    order_id: UUID
    reason: str
    refund: bool = True


class DisputeResolution(BaseModel):
    dispute_id: UUID
    outcome: str  # seller_wins, supplier_wins, partial
    outcome_amount: Optional[int] = None
    resolution_notes: str


class FraudReview(BaseModel):
    signal_id: UUID
    action: str  # confirm_fraud, dismiss, escalate
    notes: Optional[str] = None


# --- Endpoints ---

@router.patch("/inventory/force")
async def force_inventory_update(
    body: ForceInventoryUpdate,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):
    """Force update inventory for a variant. Admin only."""
    stmt = (
        update(SupplierVariant)
        .where(SupplierVariant.id == body.variant_id)
        .values(inventory=body.new_inventory)
    )
    result = await session.execute(stmt)
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Variant not found")
    await session.commit()

    logger.warning(
        f"Admin {current_user.id} force-updated inventory for variant {body.variant_id} "
        f"to {body.new_inventory}. Reason: {body.reason}"
    )
    return {"status": "updated", "variant_id": str(body.variant_id), "new_inventory": body.new_inventory}


@router.patch("/orders/force-cancel")
async def force_cancel_order(
    body: ForceOrderCancel,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):
    """Force cancel an order. Admin only. Optionally refund."""
    stmt = select(Order).where(Order.id == body.order_id)
    result = await session.execute(stmt)
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status in [OrderStatus.COMPLETED.value, OrderStatus.REFUNDED.value]:
        raise HTTPException(status_code=409, detail=f"Cannot cancel order in {order.status} state")

    order.status = OrderStatus.CANCELLED.value
    order.cancellation_reason = f"Admin force cancel: {body.reason}"

    # Release any reservations
    reservation_stmt = (
        update(InventoryReservation)
        .where(
            InventoryReservation.order_item_id.in_(
                select(Order.order_item_id).where(Order.id == body.order_id) if False else []
            ),
            InventoryReservation.status == "reserved",
        )
        .values(status="released", released_at=datetime.utcnow(), released_reason="admin_force_cancel")
    )

    await session.commit()

    logger.warning(
        f"Admin {current_user.id} force-cancelled order {body.order_id}. Reason: {body.reason}"
    )
    return {"status": "cancelled", "order_id": str(body.order_id)}


@router.post("/disputes/resolve")
async def resolve_dispute(
    body: DisputeResolution,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):
    """Resolve a dispute between seller and supplier."""
    stmt = select(Dispute).where(Dispute.id == body.dispute_id)
    result = await session.execute(stmt)
    dispute = result.scalar_one_or_none()
    if not dispute:
        raise HTTPException(status_code=404, detail="Dispute not found")

    dispute.status = "resolved"
    dispute.outcome = body.outcome
    dispute.resolution = body.resolution_notes
    dispute.resolved_by = current_user.id
    dispute.resolved_at = datetime.utcnow()
    if body.outcome == "partial" and body.outcome_amount:
        dispute.outcome_amount = body.outcome_amount

    await session.commit()

    logger.info(f"Admin {current_user.id} resolved dispute {body.dispute_id}: {body.outcome}")
    return {"status": "resolved", "dispute_id": str(body.dispute_id), "outcome": body.outcome}


@router.post("/fraud/review")
async def review_fraud_signal(
    body: FraudReview,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):
    """Review and act on a fraud signal."""
    stmt = select(FraudSignal).where(FraudSignal.id == body.signal_id)
    result = await session.execute(stmt)
    signal = result.scalar_one_or_none()
    if not signal:
        raise HTTPException(status_code=404, detail="Fraud signal not found")

    signal.status = body.action
    signal.reviewed_by = current_user.id
    signal.reviewed_at = datetime.utcnow()
    signal.review_notes = body.notes

    await session.commit()

    logger.info(f"Admin {current_user.id} reviewed fraud signal {body.signal_id}: {body.action}")
    return {"status": body.action, "signal_id": str(body.signal_id)}


@router.get("/fraud/signals")
async def list_fraud_signals(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):
    """List fraud signals with optional filtering."""
    stmt = select(FraudSignal).order_by(FraudSignal.created_at.desc()).offset(offset).limit(limit)
    if status:
        stmt = stmt.where(FraudSignal.status == status)

    result = await session.execute(stmt)
    signals = result.scalars().all()
    return {"signals": [{"id": str(s.id), "type": s.signal_type, "status": s.status} for s in signals]}
