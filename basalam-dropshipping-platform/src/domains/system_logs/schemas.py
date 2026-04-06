"""
System Logs Domain Schemas
============================
Pydantic v2 request/response schemas for system log entries.
"""
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, Field


class SystemLogCreate(BaseModel):
    """Schema for creating a system log entry."""

    level: str = Field(max_length=20)
    service: str = Field(max_length=50)
    message: str
    metadata: Optional[Dict[str, Any]] = None


class SystemLogResponse(BaseModel):
    """Schema for returning a system log entry."""

    id: UUID
    level: str
    service: str
    message: str
    metadata: Optional[Dict[str, Any]]
    created_at: datetime

    model_config = {"from_attributes": True}


class SystemLogListResponse(BaseModel):
    """Schema for a paginated list of system log entries."""

    logs: List[SystemLogResponse]
    total: int
