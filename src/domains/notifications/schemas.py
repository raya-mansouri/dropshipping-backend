"""
Notifications Domain Schemas
=============================
Pydantic schemas for notifications API
"""
from pydantic import BaseModel, ConfigDict
from uuid import UUID
from datetime import datetime
from typing import Optional, List

from src.domains.notifications.models import NotificationStatus


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    type: str
    title: str
    body: Optional[str]
    action_url: Optional[str]
    action_type: Optional[str]
    payload: Optional[dict]
    status: str
    read_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class UnreadCountResponse(BaseModel):
    unread_count: int


class MarkAllReadResponse(BaseModel):
    marked_count: int
