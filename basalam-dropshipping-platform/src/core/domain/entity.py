"""
Core Domain Entity - Base class for all domain entities
Uses UUID as primary key as per a.md requirements
"""
from datetime import datetime
from uuid import UUID, uuid4
from typing import Optional
from pydantic import BaseModel, Field


class Entity(BaseModel):
    """Base entity with UUID primary key"""
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        from_attributes = True


class AuditableEntity(Entity):
    """Entity with audit trail"""
    created_by: Optional[UUID] = None
    updated_by: Optional[UUID] = None
