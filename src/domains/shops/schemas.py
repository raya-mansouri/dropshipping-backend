"""
Shops Domain Schemas
====================
Pydantic schemas for shops API
"""
from pydantic import BaseModel, Field, ConfigDict
from uuid import UUID
from datetime import datetime
from typing import Optional
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
    status: str
    external_shop_id: Optional[str]
    connection_type: str
    last_synced_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    # Platform info (from relationship, included via computed_field or alias)
    @property
    def platform_code(self) -> Optional[str]:
        """Access platform_code from the platform relationship."""
        if hasattr(self, 'platform') and self.platform:
            return self.platform.code
        return None


# Sync
class SyncJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    integration_id: UUID
    entity_type: str
    entity_id: Optional[UUID] = None
    status: str
    retry_count: int
    error_message: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime


class SyncStatusResponse(BaseModel):
    """Response for sync status endpoint - includes both job and state info."""
    id: Optional[UUID] = None
    integration_id: UUID
    entity_type: str
    entity_id: Optional[UUID] = None
    status: str
    retry_count: int = 0
    error_message: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    # Sync state info (from SyncState)
    sync_state_status: Optional[str] = None
    sync_mode: Optional[str] = None
    total_synced: int = 0
    created_count: int = 0
    updated_count: int = 0
    failed_count: int = 0
    last_sync_timestamp: Optional[datetime] = None


class TriggerSyncRequest(BaseModel):
    entity_type: str = Field(..., pattern="^(product|inventory|order)$")


# API Request/Response (used by routes)
class ConnectRequest(BaseModel):
    """Request to connect to a platform"""
    platform_code: str = Field(..., pattern="^basalam$")
    connection_type: str = Field(..., pattern="^(oauth|api|token)$")
    credentials: dict = {}


class OAuthStartResponse(BaseModel):
    """OAuth authorization URL response"""
    authorize_url: str
    state: str
    integration_id: UUID
