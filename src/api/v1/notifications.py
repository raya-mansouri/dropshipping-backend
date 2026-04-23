"""
Notifications API Endpoints
============================
FastAPI endpoints for notification management
"""

from uuid import UUID
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db, get_current_user
from src.domains.accounts.models import User
from src.domains.notifications.models import NotificationStatus
from src.domains.notifications.schemas import (
    NotificationResponse,
    UnreadCountResponse,
    MarkAllReadResponse,
)
from src.domains.notifications.repository import NotificationRepository


# ============================================
# API Router
# ============================================

router = APIRouter(prefix="/notifications", tags=["notifications"])


# ---- Notification Endpoints ----


@router.get("/", response_model=List[NotificationResponse])
async def list_notifications(
    unread_only: bool = Query(False, description="Return only unread notifications"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List current user's notifications. Optionally filter to unread only."""
    repo = NotificationRepository(db)

    if unread_only:
        notifications = await repo.get_unread(
            current_user.id, limit=limit, offset=offset
        )
    else:
        notifications = await repo.get_by_user(
            current_user.id, limit=limit, offset=offset
        )

    return notifications


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
async def mark_notification_read(
    notification_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark a single notification as read"""
    repo = NotificationRepository(db)

    notification = await repo.get_by_id(notification_id)
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    if notification.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not your notification",
        )

    if notification.status == NotificationStatus.READ.value:
        return notification

    notification = await repo.mark_read(notification_id)
    return notification


@router.post("/mark-all-read", response_model=MarkAllReadResponse)
async def mark_all_notifications_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark all of the current user's notifications as read"""
    repo = NotificationRepository(db)

    marked_count = await repo.mark_all_read(current_user.id)
    return MarkAllReadResponse(marked_count=marked_count)


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return count of unread notifications for the current user"""
    repo = NotificationRepository(db)

    unread = await repo.get_unread(current_user.id)
    return UnreadCountResponse(unread_count=len(unread))
