"""
Fraud Detection Domain Schemas
==============================
Pydantic v2 request/response schemas for fraud signal entries.
"""
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, Field


class FraudSignalCreate(BaseModel):
    """Schema for creating a fraud signal."""

    entity_type: str = Field(max_length=50)
    entity_id: UUID
    signal_type: str = Field(max_length=50)
    severity: str = Field(max_length=20)
    data: Optional[Dict[str, Any]] = None


class FraudSignalUpdate(BaseModel):
    """Schema for updating a fraud signal status."""

    status: str = Field(max_length=20)


class FraudSignalResponse(BaseModel):
    """Schema for returning a fraud signal."""

    id: UUID
    entity_type: str
    entity_id: UUID
    signal_type: str
    severity: str
    data: Optional[Dict[str, Any]]
    status: str
    created_at: datetime
    resolved_at: Optional[datetime]

    model_config = {"from_attributes": True}


class FraudSignalListResponse(BaseModel):
    """Schema for a paginated list of fraud signals."""

    signals: List[FraudSignalResponse]
    total: int
