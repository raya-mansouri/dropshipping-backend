"""
Products Domain Schemas
=======================
Pydantic schemas for products API
"""
from pydantic import BaseModel, Field, ConfigDict
from uuid import UUID
from datetime import datetime
from typing import Optional, List
from decimal import Decimal
from enum import Enum


class ProductStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    FORBIDDEN = "forbidden"
    PENDING_REVIEW = "pending_review"
    NEEDS_REVISION = "needs_revision"


class VariantStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


# Category
class CategoryBase(BaseModel):
    name: str
    external_category_id: Optional[str] = None
    parent_id: Optional[UUID] = None
    franchise_percent: Optional[Decimal] = Field(0, ge=0, le=100)
    is_forbidden: bool = False


class CategoryResponse(CategoryBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    platform_id: Optional[UUID]
    created_at: datetime
    updated_at: datetime


# Product Media
class ProductMediaBase(BaseModel):
    media_type: str
    url: str
    sort_order: int = 0


class ProductMediaResponse(ProductMediaBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    product_id: UUID
    storage_provider: Optional[str]
    hash: Optional[str]
    status: str
    created_at: datetime


# Supplier Product
class SupplierProductBase(BaseModel):
    title: str
    description: Optional[str] = None
    category_id: Optional[UUID] = None
    has_variants: bool = False


class SupplierProductCreate(SupplierProductBase):
    shop_id: UUID
    external_product_id: Optional[str] = None


class SupplierProductUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[ProductStatus] = None


class SupplierProductResponse(SupplierProductBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    shop_id: UUID
    external_product_id: Optional[str]
    status: ProductStatus
    basalam_validation_error: Optional[dict]
    moderation_status: Optional[str]
    last_synced_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


# Product Variant
class ProductVariantBase(BaseModel):
    sku: Optional[str] = None
    external_variant_id: Optional[str] = None
    attributes: dict = {}


class ProductVariantResponse(ProductVariantBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    product_id: UUID
    created_at: datetime


# Supplier Variant
class SupplierVariantBase(BaseModel):
    cost_price: Decimal = Field(..., ge=0, description="Supplier cost price in Toman")
    inventory: int = Field(0, ge=0)


class SupplierVariantCreate(SupplierVariantBase):
    supplier_product_id: UUID
    variant_id: UUID


class SupplierVariantResponse(SupplierVariantBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    supplier_product_id: UUID
    variant_id: UUID
    status: VariantStatus
    reserved_inventory: int
    available_inventory: int
    created_at: datetime
    updated_at: datetime


# Seller Listing
class SellerListingBase(BaseModel):
    margin_percent: Decimal = Field(..., ge=0, le=100)
    sync_enabled: bool = True
    sync_price: bool = True
    sync_inventory: bool = True


class SellerListingCreate(SellerListingBase):
    supplier_product_id: UUID


class SellerListingUpdate(BaseModel):
    margin_percent: Optional[Decimal] = Field(None, ge=0, le=100)
    custom_title: Optional[str] = None
    custom_description: Optional[str] = None
    sync_enabled: Optional[bool] = None
    sync_price: Optional[bool] = None
    sync_inventory: Optional[bool] = None
    status: Optional[str] = None


class SellerListingResponse(SellerListingBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    shop_id: UUID
    supplier_product_id: UUID
    custom_title: Optional[str]
    status: str
    view_count: int
    order_count: int
    created_at: datetime
    updated_at: datetime


# Seller Variant
class SellerVariantBase(BaseModel):
    custom_price: Optional[Decimal] = Field(None, description="Seller's custom price override in Toman")
    is_enabled: bool = True


class SellerVariantResponse(SellerVariantBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    listing_id: UUID
    supplier_variant_id: UUID
    price: Decimal = Field(description="Calculated selling price in Toman")
    inventory_cache: Optional[int]
    created_at: datetime
    updated_at: datetime


# Catalog Browse
class CatalogProductFilter(BaseModel):
    shop_id: Optional[UUID] = None
    category_id: Optional[UUID] = None
    min_price: Optional[Decimal] = Field(None, description="Minimum price filter in Toman")
    max_price: Optional[Decimal] = Field(None, description="Maximum price filter in Toman")
    in_stock_only: bool = False
    search: Optional[str] = None


class CatalogProductResponse(BaseModel):
    """Product as seen in catalog"""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    title: str
    description: Optional[str]
    category_name: Optional[str]
    min_price: Decimal = Field(description="Minimum variant price in Toman")
    max_price: Decimal = Field(description="Maximum variant price in Toman")
    has_variants: bool
    images: List[ProductMediaResponse]
    supplier_name: str
    available: bool
