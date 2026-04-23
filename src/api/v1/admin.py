"""
Admin API Endpoints
===================
Administrative endpoints for managing orders, inventory, fraud, disputes,
shops, users, sync status, and webhooks.

All admin actions are recorded via AuditLogService for compliance.
"""

import asyncio

import structlog
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.deps import get_db, require_admin, get_audit_service
from src.domains.orders.models import Order, OrderStatus, OrderItem
from src.domains.products.models import SupplierVariant
from src.domains.inventory.models import InventoryReservation
from src.domains.payments.models import Dispute, Payment, SupplierPayout
from src.domains.fraud_detection.models import FraudSignal
from src.domains.shops.models import Shop, ShopIntegration, SyncState
from src.domains.accounts.models import User
from src.domains.webhooks.models import WebhookEvent, OutgoingWebhookLog
from src.domains.audit_logs.service import AuditLogService

logger = structlog.get_logger(__name__)
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
    outcome: Literal["seller_wins", "supplier_wins", "partial"]
    outcome_amount: Optional[int] = None
    resolution_notes: str


class FraudReview(BaseModel):
    signal_id: UUID
    action: Literal["confirm_fraud", "dismiss", "escalate"]
    notes: Optional[str] = None


class WebhookRetryRequest(BaseModel):
    webhook_log_id: UUID


class ShopUpdateRequest(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None


class UserUpdateRequest(BaseModel):
    is_active: Optional[bool] = None
    role: Optional[str] = None

@router.patch("/inventory/force")
async def force_inventory_update(
    body: ForceInventoryUpdate,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
    audit_service: AuditLogService = Depends(get_audit_service),
):
    """Force update inventory for a variant. Admin only."""
    stmt = select(SupplierVariant).where(SupplierVariant.id == body.variant_id)
    result = await session.execute(stmt)
    variant = result.scalar_one_or_none()
    if not variant:
        raise HTTPException(status_code=404, detail="Variant not found")

    old_inventory = variant.inventory
    variant.inventory = body.new_inventory
    await session.flush()

    await audit_service.log_action(
        entity_type="supplier_variant",
        entity_id=body.variant_id,
        action="force_inventory_update",
        actor_type="admin",
        actor_id=current_user.id,
        old_value={"inventory": old_inventory},
        new_value={"inventory": body.new_inventory},
        reason=body.reason,
    )

    logger.warning(
        "admin_force_inventory_update",
        admin_id=str(current_user.id),
        variant_id=str(body.variant_id),
        old_inventory=old_inventory,
        new_inventory=body.new_inventory,
        reason=body.reason,
    )
    return {
        "status": "updated",
        "variant_id": str(body.variant_id),
        "new_inventory": body.new_inventory,
    }


@router.patch("/orders/force-cancel")
async def force_cancel_order(
    body: ForceOrderCancel,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
    audit_service: AuditLogService = Depends(get_audit_service),
):
    """Force cancel an order. Admin only. Optionally refund."""
    stmt = select(Order).where(Order.id == body.order_id)
    result = await session.execute(stmt)
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status in [OrderStatus.COMPLETED.value, OrderStatus.REFUNDED.value]:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot cancel order in {order.status} state",
        )

    old_status = order.status
    order.status = OrderStatus.CANCELLED.value
    order.notes = f"Admin force cancel: {body.reason}"
    order.cancelled_at = datetime.now(timezone.utc)

    # Release reservations scoped to this order's items only
    reservation_stmt = (
        update(InventoryReservation)
        .where(
            InventoryReservation.status == "reserved",
            InventoryReservation.order_item_id.in_(
                select(OrderItem.id).where(OrderItem.order_id == body.order_id)
            ),
        )
        .values(
            status="released",
            released_at=datetime.now(timezone.utc),
            released_reason="admin_force_cancel",
        )
    )
    await session.execute(reservation_stmt)
    await session.flush()

    await audit_service.log_action(
        entity_type="order",
        entity_id=body.order_id,
        action="force_cancel",
        actor_type="admin",
        actor_id=current_user.id,
        old_value={"status": old_status},
        new_value={
            "status": OrderStatus.CANCELLED.value,
            "reason": body.reason,
            "refund": body.refund,
        },
        reason=body.reason,
    )

    logger.warning(
        "admin_force_cancel_order",
        admin_id=str(current_user.id),
        order_id=str(body.order_id),
        reason=body.reason,
    )
    return {"status": "cancelled", "order_id": str(body.order_id)}


@router.post("/disputes/resolve")
async def resolve_dispute(
    body: DisputeResolution,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
    audit_service: AuditLogService = Depends(get_audit_service),
):
    """Resolve a dispute between seller and supplier."""
    stmt = select(Dispute).where(Dispute.id == body.dispute_id)
    result = await session.execute(stmt)
    dispute = result.scalar_one_or_none()
    if not dispute:
        raise HTTPException(status_code=404, detail="Dispute not found")

    old_status = dispute.status
    dispute.status = "resolved"
    dispute.outcome = body.outcome
    dispute.resolution = body.resolution_notes
    dispute.resolved_by = current_user.id
    dispute.resolved_at = datetime.now(timezone.utc)
    if body.outcome == "partial" and body.outcome_amount:
        dispute.outcome_amount = body.outcome_amount

    await session.flush()

    await audit_service.log_action(
        entity_type="dispute",
        entity_id=body.dispute_id,
        action="resolve",
        actor_type="admin",
        actor_id=current_user.id,
        old_value={"status": old_status},
        new_value={
            "status": "resolved",
            "outcome": body.outcome,
            "outcome_amount": body.outcome_amount,
        },
        reason=body.resolution_notes,
    )

    logger.info(
        "admin_resolved_dispute",
        admin_id=str(current_user.id),
        dispute_id=str(body.dispute_id),
        outcome=body.outcome,
    )
    return {
        "status": "resolved",
        "dispute_id": str(body.dispute_id),
        "outcome": body.outcome,
    }


@router.post("/fraud/review")
async def review_fraud_signal(
    body: FraudReview,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
    audit_service: AuditLogService = Depends(get_audit_service),
):
    """Review and act on a fraud signal."""
    stmt = select(FraudSignal).where(FraudSignal.id == body.signal_id)
    result = await session.execute(stmt)
    signal = result.scalar_one_or_none()
    if not signal:
        raise HTTPException(status_code=404, detail="Fraud signal not found")

    old_status = signal.status
    signal.status = body.action
    if body.action in ("confirm_fraud", "dismiss", "escalate"):
        signal.resolved_at = datetime.now(timezone.utc)

    await session.flush()

    await audit_service.log_action(
        entity_type="fraud_signal",
        entity_id=body.signal_id,
        action="review",
        actor_type="admin",
        actor_id=current_user.id,
        old_value={"status": old_status},
        new_value={"status": body.action, "notes": body.notes},
        reason=body.notes,
    )

    logger.info(
        "admin_reviewed_fraud_signal",
        admin_id=str(current_user.id),
        signal_id=str(body.signal_id),
        action=body.action,
    )
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
    return {
        "signals": [
            {"id": str(s.id), "type": s.signal_type, "status": s.status}
            for s in signals
        ]
    }


@router.get("/sync/status")
async def get_sync_status(
    session: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
    audit_service: AuditLogService = Depends(get_audit_service),
):
    """Get status of product/inventory sync operations.

    Returns sync metrics for all shops.
    """
    # Single query: JOIN shops → integrations → sync_states to avoid N+1
    stmt = (
        select(Shop, ShopIntegration, SyncState)
        .outerjoin(ShopIntegration, ShopIntegration.shop_id == Shop.id)
        .outerjoin(SyncState, SyncState.integration_id == ShopIntegration.id)
        .options(selectinload(ShopIntegration.platform))
        .order_by(SyncState.last_sync_timestamp.desc())
    )
    result = await session.execute(stmt)
    rows = result.all()

    # Group by shop, then by integration
    shops_map: dict = {}
    integrations_map: dict = {}
    for shop, integration, sync_state in rows:
        shop_id = str(shop.id)
        if shop_id not in shops_map:
            shops_map[shop_id] = {
                "shop_id": shop_id,
                "shop_name": shop.name,
                "shop_role": shop.shop_role,
                "platform": None,
                "sync_states": [],
                "last_synced_at": None,
            }

        if integration is None:
            continue

        int_key = (shop_id, str(integration.id))
        if int_key not in integrations_map:
            integrations_map[int_key] = True
            # Set platform from eagerly loaded relationship (no extra query)
            if shops_map[shop_id]["platform"] is None and integration.platform:
                shops_map[shop_id]["platform"] = integration.platform.code

        if sync_state is not None:
            shops_map[shop_id]["sync_states"].append({
                "entity_type": sync_state.entity_type,
                "status": sync_state.status,
                "last_synced_at": sync_state.last_sync_timestamp.isoformat() if sync_state.last_sync_timestamp else None,
                "total_synced": sync_state.total_synced,
                "failed_count": sync_state.failed_count,
            })

    # Compute last_synced_at per shop
    results = []
    for shop_data in shops_map.values():
        sync_timestamps = [
            s["last_synced_at"] for s in shop_data["sync_states"] if s["last_synced_at"]
        ]
        shop_data["last_synced_at"] = max(sync_timestamps, default=None)
        results.append(shop_data)

    await audit_service.log_action(
        entity_type="sync_status",
        entity_id=UUID("00000000-0000-0000-0000-000000000000"),
        action="viewed",
        actor_type="admin",
        actor_id=current_user.id,
        new_value={"shops_checked": len(results)},
    )

    return {"sync_statuses": results}


@router.post("/webhook/retry")
async def retry_webhook(
    body: WebhookRetryRequest,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
    audit_service: AuditLogService = Depends(get_audit_service),
):
    """Retry a failed webhook delivery (incoming or outgoing)."""
    # Try incoming WebhookEvent first
    stmt = select(WebhookEvent).where(WebhookEvent.id == body.webhook_log_id)
    result = await session.execute(stmt)
    log_entry = result.scalar_one_or_none()

    if log_entry:
        if log_entry.status == "completed":
            raise HTTPException(
                status_code=409, detail="Webhook already completed successfully"
            )

        old_status = log_entry.status
        log_entry.status = "received"
        log_entry.retry_count = 0
        log_entry.processed_at = None
        log_entry.error_message = None
        log_entry.error_trace = None
        await session.flush()

        await audit_service.log_action(
            entity_type="webhook_event",
            entity_id=body.webhook_log_id,
            action="retry_requested",
            actor_type="admin",
            actor_id=current_user.id,
            old_value={"status": old_status, "retry_count": log_entry.retry_count},
            new_value={"status": "received", "retry_count": 0},
        )

        return {
            "status": "retry_scheduled",
            "webhook_log_id": str(body.webhook_log_id),
            "type": "incoming",
        }

    # Try outgoing OutgoingWebhookLog
    out_stmt = select(OutgoingWebhookLog).where(
        OutgoingWebhookLog.id == body.webhook_log_id
    )
    out_result = await session.execute(out_stmt)
    out_entry = out_result.scalar_one_or_none()

    if out_entry:
        if out_entry.status == "sent":
            raise HTTPException(
                status_code=409, detail="Outgoing webhook already sent successfully"
            )

        old_status = out_entry.status
        out_entry.status = "pending"
        out_entry.retry_count = 0
        out_entry.last_error = None
        out_entry.next_retry_at = None
        await session.flush()

        await audit_service.log_action(
            entity_type="outgoing_webhook_log",
            entity_id=body.webhook_log_id,
            action="retry_requested",
            actor_type="admin",
            actor_id=current_user.id,
            old_value={"status": old_status},
            new_value={"status": "pending", "retry_count": 0},
        )

        return {
            "status": "retry_scheduled",
            "webhook_log_id": str(body.webhook_log_id),
            "type": "outgoing",
        }

    raise HTTPException(status_code=404, detail="Webhook log not found")


@router.get("/shops")
async def list_shops(
    status: Optional[str] = None,
    shop_role: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
    audit_service: AuditLogService = Depends(get_audit_service),
):
    """List all shops with optional filtering."""
    query = select(Shop)
    if status:
        query = query.where(Shop.status == status)
    if shop_role:
        query = query.where(Shop.shop_role == shop_role)

    query = query.order_by(Shop.created_at.desc()).offset(offset).limit(limit)
    shops_result = await session.execute(query)
    shop_list = shops_result.scalars().all()

    await audit_service.log_action(
        entity_type="shop",
        entity_id=UUID("00000000-0000-0000-0000-000000000000"),
        action="list",
        actor_type="admin",
        actor_id=current_user.id,
        new_value={
            "count": len(shop_list),
            "filters": {"status": status, "shop_role": shop_role},
        },
    )

    return {
        "shops": [
            {
                "id": str(shop.id),
                "name": shop.name,
                "shop_role": shop.shop_role,
                "status": shop.status,
                "created_at": shop.created_at.isoformat(),
            }
            for shop in shop_list
        ],
        "total": len(shop_list),
    }


@router.patch("/shops/{shop_id}")
async def update_shop(
    shop_id: UUID,
    body: ShopUpdateRequest,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
    audit_service: AuditLogService = Depends(get_audit_service),
):
    """Update shop status/active state. Admin only."""
    shop = await session.get(Shop, shop_id)
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    old_values = {}
    if body.name is not None:
        old_values["name"] = shop.name
        shop.name = body.name
    if body.status is not None:
        old_values["status"] = shop.status
        shop.status = body.status

    shop.updated_at = datetime.now(timezone.utc)
    await session.flush()

    await audit_service.log_action(
        entity_type="shop",
        entity_id=shop_id,
        action="updated",
        actor_type="admin",
        actor_id=current_user.id,
        old_value=old_values if old_values else None,
        new_value=body.model_dump(exclude_none=True),
    )

    return {
        "id": str(shop.id),
        "name": shop.name,
        "shop_role": shop.shop_role,
        "status": shop.status,
    }


@router.get("/users")
async def list_users(
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
    audit_service: AuditLogService = Depends(get_audit_service),
):
    """List all users with optional filtering."""
    query = select(User)
    if role:
        query = query.where(User.role == role)
    if is_active is not None:
        query = query.where(User.is_active == is_active)

    query = query.order_by(User.created_at.desc()).offset(offset).limit(limit)
    users_result = await session.execute(query)
    user_list = users_result.scalars().all()

    await audit_service.log_action(
        entity_type="user",
        entity_id=UUID("00000000-0000-0000-0000-000000000000"),
        action="list",
        actor_type="admin",
        actor_id=current_user.id,
        new_value={
            "count": len(user_list),
            "filters": {"role": role, "is_active": is_active},
        },
    )

    return {
        "users": [
            {
                "id": str(user.id),
                "phone": user.phone,
                "full_name": user.full_name,
                "role": user.role,
                "is_active": user.is_active,
                "created_at": user.created_at.isoformat(),
            }
            for user in user_list
        ],
        "total": len(user_list),
    }


@router.patch("/users/{user_id}")
async def update_user(
    user_id: UUID,
    body: UserUpdateRequest,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
    audit_service: AuditLogService = Depends(get_audit_service),
):
    """Update user status/role. Admin only."""
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    old_values = {}
    if body.is_active is not None:
        old_values["is_active"] = user.is_active
        user.is_active = body.is_active
    if body.role is not None:
        old_values["role"] = user.role
        user.role = body.role

    user.updated_at = datetime.now(timezone.utc)
    await session.flush()

    await audit_service.log_action(
        entity_type="user",
        entity_id=user_id,
        action="updated",
        actor_type="admin",
        actor_id=current_user.id,
        old_value=old_values if old_values else None,
        new_value={"is_active": user.is_active, "role": user.role},
    )

    return {
        "id": str(user.id),
        "phone": user.phone,
        "role": user.role,
        "is_active": user.is_active,
    }


# --- System-wide read endpoints ---
# TODO: Replace Dict[str, Any] response_model with proper Pydantic schemas
# for list_all_orders, list_all_payments, and list_all_disputes.


@router.get("/orders", response_model=Dict[str, Any])
async def list_all_orders(
    status: Optional[str] = None,
    shop_id: Optional[UUID] = None,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):
    """List all orders across all shops. Admin only."""
    stmt = select(Order).order_by(Order.created_at.desc()).offset(offset).limit(limit)
    if status:
        stmt = stmt.where(Order.status == status)
    if shop_id:
        stmt = stmt.where(Order.shop_id == shop_id)

    result = await session.execute(stmt)
    orders = result.scalars().all()

    return {
        "orders": [
            {
                "id": str(o.id),
                "shop_id": str(o.shop_id),
                "status": o.status,
                "total_price": float(o.total_price) if o.total_price else 0,
                "shipping_price": float(o.shipping_price) if o.shipping_price else 0,
                "discount": float(o.discount) if o.discount else 0,
                "created_at": o.created_at.isoformat() if o.created_at else None,
            }
            for o in orders
        ],
        "total": len(orders),
    }


@router.get("/dashboard")
async def admin_dashboard(
    session: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):
    """Aggregated system-wide stats for the admin dashboard."""
    yesterday = datetime.now(timezone.utc) - timedelta(hours=24)

    (
        total_orders_result,
        total_revenue_result,
        active_shops_result,
        total_users_result,
        recent_orders_result,
        pending_payouts_result,
    ) = await asyncio.gather(
        session.execute(select(func.count(Order.id))),
        session.execute(select(func.coalesce(func.sum(Order.total_price), 0))),
        session.execute(select(func.count(Shop.id)).where(Shop.status == "active")),
        session.execute(select(func.count(User.id))),
        session.execute(
            select(func.count(Order.id)).where(Order.created_at >= yesterday)
        ),
        session.execute(
            select(func.coalesce(func.sum(SupplierPayout.amount), 0)).where(
                SupplierPayout.status == "pending"
            )
        ),
    )

    return {
        "total_orders": total_orders_result.scalar() or 0,
        "total_revenue": float(total_revenue_result.scalar() or 0),
        "active_shops": active_shops_result.scalar() or 0,
        "total_users": total_users_result.scalar() or 0,
        "recent_orders_count": recent_orders_result.scalar() or 0,
        "pending_payouts_amount": float(pending_payouts_result.scalar() or 0),
    }


@router.get("/payments", response_model=Dict[str, Any])
async def list_all_payments(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):
    """List all payments across all shops. Admin only."""
    stmt = (
        select(Payment).order_by(Payment.created_at.desc()).offset(offset).limit(limit)
    )
    if status:
        stmt = stmt.where(Payment.status == status)

    result = await session.execute(stmt)
    payments = result.scalars().all()

    return {
        "payments": [
            {
                "id": str(p.id),
                "order_id": str(p.order_id),
                "status": p.status,
                "seller_paid_amount": float(p.seller_paid_amount)
                if p.seller_paid_amount
                else 0,
                "supplier_payable_amount": float(p.supplier_payable_amount)
                if p.supplier_payable_amount
                else 0,
                "platform_fee": float(p.platform_fee) if p.platform_fee else 0,
                "gateway": p.gateway,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in payments
        ],
        "total": len(payments),
    }


@router.get("/disputes", response_model=Dict[str, Any])
async def list_all_disputes(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):
    """List all disputes across all orders. Admin only."""
    stmt = (
        select(Dispute).order_by(Dispute.created_at.desc()).offset(offset).limit(limit)
    )
    if status:
        stmt = stmt.where(Dispute.status == status)

    result = await session.execute(stmt)
    disputes = result.scalars().all()

    return {
        "disputes": [
            {
                "id": str(d.id),
                "order_item_id": str(d.order_item_id),
                "opened_by": d.opened_by,
                "status": d.status,
                "reason": d.reason,
                "outcome": d.outcome,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in disputes
        ],
        "total": len(disputes),
    }
