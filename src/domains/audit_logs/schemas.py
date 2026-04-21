"""
AuditLog Schemas
================
Pydantic v2 request/response schemas for audit log entries.
"""
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, Field


class AuditLogCreate(BaseModel):
    """Schema for creating an audit log entry."""

    entity_type: str = Field(max_length=50)
    entity_id: UUID
    action: str = Field(max_length=50)
    actor_type: str = Field(max_length=20)
    actor_id: UUID
    old_value: Optional[Dict[str, Any]] = None
    new_value: Optional[Dict[str, Any]] = None
    reason: Optional[str] = None


class AuditLogResponse(BaseModel):
    """Schema for returning an audit log entry."""

    id: UUID
    entity_type: str
    entity_id: UUID
    action: str
    actor_type: str
    actor_id: Optional[UUID]
    old_value: Optional[Dict[str, Any]]
    new_value: Optional[Dict[str, Any]]
    reason: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditLogListResponse(BaseModel):
    """Schema for a paginated list of audit log entries."""

    logs: List[AuditLogResponse]
    total: int
