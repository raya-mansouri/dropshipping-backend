"""
Shop API Endpoints
==================
FastAPI endpoints for shop management
"""
from uuid import UUID
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_active_user
from src.core.database import get_db
from src.core.repository.unit_of_work import UnitOfWork
from src.domains.shops.schemas import (
    ShopCreate,
    ShopResponse,
    ShopIntegrationResponse,
    ConnectRequest,
    OAuthStartRequest,
    OAuthStartResponse,
    OAuthCallbackRequest,
    SyncJobResponse,
)
from src.domains.shops.service import ShopService, IntegrationService, SyncService


router = APIRouter(prefix="/shops", tags=["shops"])


# ---- Shop CRUD ----

@router.post("/", response_model=ShopResponse, status_code=status.HTTP_201_CREATED)
async def create_shop(
    shop_data: ShopCreate,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Create a new shop. Role can ONLY be 'supplier' or 'seller'."""
    service = ShopService(session)
    try:
        shop = await service.create_shop(
            account_id=shop_data.account_id,
            name=shop_data.name,
            role=shop_data.shop_role.value,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return shop


@router.get("/{shop_id}", response_model=ShopResponse)
async def get_shop(
    shop_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Get shop by ID."""
    service = ShopService(session)
    shop = await service.get_shop(shop_id)
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    return shop


@router.get("/", response_model=List[ShopResponse])
async def list_shops(
    account_id: UUID = Query(...),
    shop_role: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """List shops for account, optionally filtered by role."""
    service = ShopService(session)

    if shop_role:
        shops = await service._repository.get_by_role(account_id, shop_role)
    else:
        shops = await service.list_shops_by_account(account_id)
    return shops


@router.delete("/{shop_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shop(
    shop_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Soft-delete a shop (sets status to 'disabled')."""
    service = ShopService(session)
    deleted = await service.disable_shop(shop_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Shop not found")


# ---- Integration Endpoints ----

@router.post("/{shop_id}/connect", response_model=ShopIntegrationResponse)
async def connect_platform(
    shop_id: UUID,
    connect_data: ConnectRequest,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Connect shop to a platform (Basalam, Shopify, etc.)."""
    service = IntegrationService(session)

    # Verify shop exists
    shop_service = ShopService(session)
    shop = await shop_service.get_shop(shop_id)
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    async with UnitOfWork(session):
        try:
            integration = await service.connect_shop(
                shop_id=shop_id,
                platform_code=connect_data.platform_code,
                credentials=connect_data.credentials,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    return integration


@router.get("/{shop_id}/integrations", response_model=List[ShopIntegrationResponse])
async def list_integrations(
    shop_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """List all integrations for a shop."""
    service = IntegrationService(session)
    return await service.list_integrations(shop_id)


@router.post("/{shop_id}/integrations/{integration_id}/disconnect")
async def disconnect_integration(
    shop_id: UUID,
    integration_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Disconnect a platform integration."""
    service = IntegrationService(session)

    integration_repo = service._integration_repository
    integration = await integration_repo.get_by_id(integration_id)
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    async with UnitOfWork(session):
        disconnected = await service.disconnect_shop(
            shop_id=shop_id,
            platform_id=integration.platform_id,
        )
    if not disconnected:
        raise HTTPException(status_code=404, detail="Integration not found")
    return {"status": "disconnected"}


# ---- OAuth Endpoints ----

@router.post("/{shop_id}/oauth/start", response_model=OAuthStartResponse)
async def start_oauth(
    shop_id: UUID,
    oauth_data: OAuthStartRequest,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Start OAuth flow. Returns authorization URL to redirect user."""
    service = IntegrationService(session)

    # Verify shop exists
    shop_service = ShopService(session)
    shop = await shop_service.get_shop(shop_id)
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    try:
        result = await service.handle_oauth_callback(
            shop_id=shop_id,
            platform_code=oauth_data.platform_code.value,
            code="",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Return OAuth start data — the service generates the URL/state
    return OAuthStartResponse(
        authorize_url=result.get("authorize_url", ""),
        state=result.get("state", ""),
        integration_id=result.get("integration_id", ""),
    )


@router.post("/{shop_id}/oauth/callback", response_model=ShopIntegrationResponse)
async def oauth_callback(
    shop_id: UUID,
    callback_data: OAuthCallbackRequest,
    session: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Handle OAuth callback — exchange code for tokens."""
    service = IntegrationService(session)

    try:
        integration = await service.handle_oauth_callback(
            shop_id=shop_id,
            platform_code="",  # Extracted from state
            code=callback_data.code,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return integration


# ---- Sync Endpoints ----

@router.post("/{shop_id}/sync/products")
async def sync_products(
    shop_id: UUID,
    integration_id: UUID = Query(...),
    session: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Trigger manual product sync for integration."""
    service = SyncService(session)

    try:
        job = await service.create_sync_job(
            integration_id=integration_id,
            entity_type="product",
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return SyncJobResponse.model_validate(job)


@router.get("/{shop_id}/sync/status")
async def get_sync_status(
    shop_id: UUID,
    integration_id: UUID = Query(...),
    session: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Get sync status for integration."""
    service = SyncService(session)
    return await service.get_sync_status(integration_id)
