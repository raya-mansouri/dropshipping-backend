"""
Shop API Endpoints
==================
FastAPI endpoints for shop management
"""
from uuid import UUID
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from datetime import datetime

# These would be imported from actual modules
# from src.domains.shops.service import ShopService
# from src.integrations.shop.ports import ShopConnectorRegistryPort


# ============================================
# Request/Response Models
# ============================================

class ShopCreate(BaseModel):
    """Request to create a new shop"""
    name: str = Field(..., min_length=1, max_length=255)
    shop_role: str = Field(..., pattern="^(supplier|seller)$")  # Only supplier OR seller


class ShopResponse(BaseModel):
    """Shop response"""
    id: UUID
    account_id: UUID
    name: str
    shop_role: str
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class ShopIntegrationResponse(BaseModel):
    """Integration response"""
    id: UUID
    shop_id: UUID
    platform_id: UUID
    platform_code: str
    external_shop_id: Optional[str]
    connection_type: str
    status: str
    last_synced_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class ConnectRequest(BaseModel):
    """Request to connect to a platform"""
    platform_code: str = Field(..., pattern="^(basalam|shopify|woocommerce)$")
    connection_type: str = Field(..., pattern="^(oauth|api|token)$")
    credentials: dict = {}  # API keys, tokens, etc.


class OAuthStartResponse(BaseModel):
    """OAuth authorization URL"""
    authorize_url: str
    state: str
    integration_id: UUID


class OAuthCallbackRequest(BaseModel):
    """OAuth callback with authorization code"""
    code: str
    state: str


# ============================================
# API Router
# ============================================

router = APIRouter(prefix="/shops", tags=["shops"])


@router.post("/", response_model=ShopResponse, status_code=status.HTTP_201_CREATED)
async def create_shop(
    shop_data: ShopCreate,
    account_id: UUID  # Would come from auth
):
    """
    Create a new shop
    
    Shop role can ONLY be 'supplier' or 'seller' (not both)
    """
    # Implementation would call ShopService
    # service = ShopService()
    # shop = await service.create_shop(account_id, shop_data)
    # return shop
    pass


@router.get("/{shop_id}", response_model=ShopResponse)
async def get_shop(shop_id: UUID):
    """Get shop by ID"""
    pass


@router.get("/", response_model=List[ShopResponse])
async def list_shops(
    account_id: UUID,  # From auth
    shop_role: Optional[str] = None,
    status: Optional[str] = None
):
    """List shops for account"""
    pass


@router.delete("/{shop_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shop(shop_id: UUID):
    """Delete a shop (soft delete)"""
    pass


# ---- Integration Endpoints ----

@router.post("/{shop_id}/connect", response_model=ShopIntegrationResponse)
async def connect_platform(
    shop_id: UUID,
    connect_data: ConnectRequest
):
    """
    Connect shop to a platform (Basalam, Shopify, etc.)
    
    Returns integration details based on connection type
    """
    pass


@router.get("/{shop_id}/integrations", response_model=List[ShopIntegrationResponse])
async def list_integrations(shop_id: UUID):
    """List all integrations for a shop"""
    pass


@router.post("/{shop_id}/integrations/{integration_id}/disconnect")
async def disconnect_integration(
    shop_id: UUID,
    integration_id: UUID
):
    """Disconnect a platform integration"""
    pass


# ---- OAuth Endpoints ----

@router.post("/{shop_id}/oauth/start", response_model=OAuthStartResponse)
async def start_oauth(
    shop_id: UUID,
    platform_code: str
):
    """
    Start OAuth flow for Basalam connection
    
    Returns authorization URL to redirect user
    """
    pass


@router.post("/{shop_id}/oauth/callback")
async def oauth_callback(
    shop_id: UUID,
    callback_data: OAuthCallbackRequest
):
    """
    Handle OAuth callback from Basalam
    
    Exchange code for tokens and complete connection
    """
    pass


# ---- Sync Endpoints ----

@router.post("/{shop_id}/sync/products")
async def sync_products(
    shop_id: UUID,
    integration_id: UUID
):
    """
    Trigger manual product sync for integration
    """
    pass


@router.get("/{shop_id}/sync/status")
async def get_sync_status(shop_id: UUID, integration_id: UUID):
    """Get sync status for integration"""
    pass
