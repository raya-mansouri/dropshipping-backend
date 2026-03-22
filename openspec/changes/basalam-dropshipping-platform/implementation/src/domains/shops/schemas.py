"""
Shops Domain Schemas
====================
Pydantic schemas for shops API
"""
from pydantic import BaseModel, Field, ConfigDict
from uuid import UUID
from datetime import datetime
from typing import Optional, List
from enum import Enum


# Enums
class ShopRole(str, Enum):
    SUPPLIER = "supplier"
    SELLER = "seller"


class ConnectionType(str, Enum):
    OAUTH = "oauth"
    API = "api"
    TOKEN = "token"
    MANUAL = "manual"


class PlatformCode(str, Enum):
    BASALAM = "basalam"
    SHOPIFY = "shopify"
    WOOCOMMERCE = "woocommerce"


# Platform
class PlatformBase(BaseModel):
    code: str
    name: str
    platform_type: str


class PlatformResponse(PlatformBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    created_at: datetime
    updated_at: datetime


# Shop
class ShopBase(BaseModel):
    name: str
    shop_role: ShopRole
    settings: Optional[dict] = {}


class ShopCreate(ShopBase):
    account_id: UUID


class ShopUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    settings: Optional[dict] = None


class ShopResponse(ShopBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    account_id: UUID
    status: str
    created_at: datetime
    updated_at: datetime


# Shop Integration
class ShopIntegrationBase(BaseModel):
    connection_type: ConnectionType
    external_shop_id: Optional[str] = None


class ShopIntegrationCreate(ShopIntegrationBase):
    platform_id: UUID
    shop_id: UUID


class OAuthStartRequest(BaseModel):
    platform_code: PlatformCode


class OAuthCallbackRequest(BaseModel):
    code: str
    state: str


class ShopIntegrationResponse(ShopIntegrationBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    shop_id: UUID
    platform_id: UUID
    platform_code: str
    status: str
    last_synced_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


# Sync
class SyncJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    integration_id: UUID
    entity_type: str
    status: str
    retry_count: int
    error_message: Optional[str]
    scheduled_at: Optional[datetime]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime


class TriggerSyncRequest(BaseModel):
    entity_type: str = Field(..., pattern="^(product|inventory|order)$")
