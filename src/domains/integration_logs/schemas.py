"""
Integration Logs Domain Schemas
=================================
Pydantic v2 request/response schemas for integration log entries.
"""
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, Field


class IntegrationLogCreate(BaseModel):
    """Schema for creating an integration log entry."""

    integration_id: UUID
    action: str = Field(max_length=50)
    status: str = Field(max_length=20)
    request_data: Optional[Dict[str, Any]] = None
    response_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None


class IntegrationLogResponse(BaseModel):
    """Schema for returning an integration log entry."""

    id: UUID
    integration_id: UUID
    action: str
    status: str
    request_data: Optional[Dict[str, Any]]
    response_data: Optional[Dict[str, Any]]
    error_message: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class IntegrationLogListResponse(BaseModel):
    """Schema for a paginated list of integration log entries."""

    logs: List[IntegrationLogResponse]
    total: int
