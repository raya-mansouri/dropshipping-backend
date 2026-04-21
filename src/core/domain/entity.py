"""
Core Domain Entity - Base class for all domain entities
Uses UUID as primary key as per a.md requirements
"""
from datetime import datetime, timezone
from uuid import UUID, uuid4
from typing import Optional
from pydantic import BaseModel, Field


class Entity(BaseModel):
    """Base entity with UUID primary key"""
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    class Config:
        from_attributes = True


class AuditableEntity(Entity):
    """Entity with audit trail"""
    created_by: Optional[UUID] = None
    updated_by: Optional[UUID] = None
