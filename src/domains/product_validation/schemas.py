"""
Product Validation Domain Schemas
=================================
Pydantic v2 request/response schemas for product validation,
keyword filtering, and image moderation.
"""
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, Field


# ---- Product Validation Log Schemas ----

class ProductValidationCreate(BaseModel):
    """Schema for creating a product validation log."""
    supplier_product_id: UUID
    validation_type: str = Field(max_length=50)
    status: str = Field(max_length=20)
    error_code: Optional[str] = Field(default=None, max_length=50)
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class ProductValidationResponse(BaseModel):
    """Schema for returning a product validation log."""
    id: UUID
    supplier_product_id: UUID
    validation_type: str
    status: str
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ProductValidationListResponse(BaseModel):
    """Schema for a paginated list of product validation logs."""
    logs: List[ProductValidationResponse]
    total: int


# ---- Forbidden Keyword Schemas ----

class ForbiddenKeywordCreate(BaseModel):
    """Schema for creating a forbidden keyword."""
    keyword: str = Field(max_length=500)
    category: str = Field(default="prohibited", pattern=r"^(prohibited|restricted|review_required)$")
    severity: str = Field(default="high", pattern=r"^(low|medium|high|critical)$")
    language: str = Field(default="fa", max_length=10)
    is_regex: bool = False
    description: Optional[str] = None


class ForbiddenKeywordUpdate(BaseModel):
    """Schema for updating a forbidden keyword."""
    keyword: Optional[str] = Field(default=None, max_length=500)
    category: Optional[str] = Field(default=None, pattern=r"^(prohibited|restricted|review_required)$")
    severity: Optional[str] = Field(default=None, pattern=r"^(low|medium|high|critical)$")
    is_active: Optional[bool] = None
    description: Optional[str] = None


class ForbiddenKeywordResponse(BaseModel):
    """Schema for returning a forbidden keyword."""
    id: UUID
    keyword: str
    category: str
    severity: str
    language: str
    is_regex: bool
    is_active: bool
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ForbiddenKeywordListResponse(BaseModel):
    """Schema for a paginated list of forbidden keywords."""
    keywords: List[ForbiddenKeywordResponse]
    total: int


# ---- Product Scan Schemas ----

class ProductScanRequest(BaseModel):
    """Schema for requesting a product scan."""
    title: str
    description: Optional[str] = ""


class ProductScanResponse(BaseModel):
    """Schema for returning scan results."""
    is_clean: bool
    status: str  # approved, pending_review, flagged, rejected
    matches: List[Dict[str, Any]]
    severity: Optional[str] = None


# ---- Moderation Schemas ----

class ModerationStatusUpdate(BaseModel):
    """Schema for updating moderation status from Basalam."""
    product_id: UUID
    moderation_status: str = Field(pattern=r"^(pending_review|approved|rejected)$")
    reason: Optional[str] = None
    rejected_images: Optional[List[UUID]] = None


class ModerationStatusResponse(BaseModel):
    """Schema for returning moderation status."""
    product_id: UUID
    moderation_status: str
    status: Optional[str] = None
    basalam_validation_error: Optional[Dict[str, Any]] = None
