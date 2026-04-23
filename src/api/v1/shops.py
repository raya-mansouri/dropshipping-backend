"""
Shop API Endpoints
==================
FastAPI endpoints for shop management
"""

from uuid import UUID
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import (
    get_current_active_user,
    verify_account_ownership,
    verify_shop_ownership,
)
from src.api.deps import get_db
from src.core.repository.unit_of_work import UnitOfWork
from src.domains.accounts.models import User
from src.domains.shops.schemas import (
    ShopCreate,
    ShopResponse,
    ShopIntegrationResponse,
    ConnectRequest,
    OAuthStartRequest,
    OAuthStartResponse,
    OAuthCallbackRequest,
    SyncJobResponse,
    SyncStatusResponse,
)
from src.domains.shops.service import ShopService, IntegrationService, SyncService
from src.core.events import ProductSyncRequested
from src.core.events.publisher import EventPublisher
from src.core.config import get_settings as _get_settings
import structlog

logger = structlog.get_logger(__name__)


router = APIRouter(prefix="/shops", tags=["shops"])


# ---- Shop CRUD ----


@router.post("/", response_model=ShopResponse, status_code=status.HTTP_201_CREATED)
async def create_shop(
    shop_data: ShopCreate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create a new shop. Role can ONLY be 'supplier' or 'seller'."""
    await verify_account_ownership(shop_data.account_id, current_user, session)

    service = ShopService(session)
    try:
        shop = await service.create_shop(
            account_id=shop_data.account_id,
            name=shop_data.name,
            role=shop_data.shop_role.value,
        )
    except ValueError as e:
        error_msg = str(e)
        if "already exists" in error_msg:
            raise HTTPException(status_code=409, detail=error_msg)
        raise HTTPException(status_code=422, detail=error_msg)
    return shop


@router.get("/{shop_id}", response_model=ShopResponse)
async def get_shop(
    shop_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get shop by ID."""
    shop = await verify_shop_ownership(shop_id, current_user, session)
    return shop


@router.get("/", response_model=List[ShopResponse])
async def list_shops(
    account_id: Optional[UUID] = Query(None),
    shop_role: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List shops for the current user's accounts, optionally filtered by account/role."""
    service = ShopService(session)

    if account_id:
        await verify_account_ownership(account_id, current_user, session)
        if shop_role:
            shops = await service._repository.get_by_role(account_id, shop_role)
        else:
            shops = await service.list_shops_by_account(account_id)
    else:
        shops = await service._repository.get_by_owner(current_user.id)
        if shop_role:
            shops = [s for s in shops if s.shop_role == shop_role]
    return shops


@router.delete("/{shop_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shop(
    shop_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Soft-delete a shop (sets status to 'disabled')."""
    await verify_shop_ownership(shop_id, current_user, session)
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
    current_user: User = Depends(get_current_active_user),
):
    """Connect shop to Basalam platform. One integration per shop."""
    await verify_shop_ownership(shop_id, current_user, session)

    service = IntegrationService(session)
    async with UnitOfWork(session):
        try:
            integration = await service.connect_shop(
                shop_id=shop_id,
                platform_code=connect_data.platform_code,
                credentials={
                    **connect_data.credentials,
                    "connection_type": connect_data.connection_type,
                },
            )
        except ValueError as e:
            error_msg = str(e)
            if "already has an active integration" in error_msg:
                raise HTTPException(status_code=409, detail=error_msg)
            raise HTTPException(status_code=400, detail=error_msg)
        except Exception:
            # Webhook registration failed — retry without webhooks
            try:
                integration = await service.connect_shop(
                    shop_id=shop_id,
                    platform_code=connect_data.platform_code,
                    credentials={
                        **connect_data.credentials,
                        "connection_type": connect_data.connection_type,
                    },
                    register_webhooks=False,
                )
            except ValueError as e:
                error_msg = str(e)
                if "already has an active integration" in error_msg:
                    raise HTTPException(status_code=409, detail=error_msg)
                raise HTTPException(status_code=400, detail=error_msg)
    return integration


@router.get("/{shop_id}/integrations", response_model=List[ShopIntegrationResponse])
async def list_integrations(
    shop_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List integrations for a shop (max 1 per shop)."""
    await verify_shop_ownership(shop_id, current_user, session)
    service = IntegrationService(session)
    return await service.list_integrations(shop_id)


@router.post("/{shop_id}/integrations/{integration_id}/disconnect")
async def disconnect_integration(
    shop_id: UUID,
    integration_id: UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Disconnect a platform integration."""
    await verify_shop_ownership(shop_id, current_user, session)

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
    current_user: User = Depends(get_current_active_user),
):
    """Start OAuth flow. Returns authorization URL to redirect user."""
    await verify_shop_ownership(shop_id, current_user, session)

    service = IntegrationService(session)
    async with UnitOfWork(session):
        try:
            result = await service.start_oauth(
                shop_id=shop_id,
                platform_code=oauth_data.platform_code.value,
            )
        except ValueError as e:
            error_msg = str(e)
            if "already has an active integration" in error_msg:
                raise HTTPException(status_code=409, detail=error_msg)
            raise HTTPException(status_code=400, detail=error_msg)

    return OAuthStartResponse(
        authorize_url=result["authorize_url"],
        state=result["state"],
        integration_id=result["integration_id"],
    )


@router.post("/{shop_id}/oauth/callback", response_model=ShopIntegrationResponse)
async def oauth_callback(
    shop_id: UUID,
    callback_data: OAuthCallbackRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Handle OAuth callback — exchange code for tokens."""
    await verify_shop_ownership(shop_id, current_user, session)

    service = IntegrationService(session)
    async with UnitOfWork(session):
        try:
            integration = await service.handle_oauth_callback(
                shop_id=shop_id,
                code=callback_data.code,
                state=callback_data.state,
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
    current_user: User = Depends(get_current_active_user),
):
    """Trigger manual product sync for integration."""
    await verify_shop_ownership(shop_id, current_user, session)

    service = SyncService(session)

    try:
        job = await service.create_sync_job(
            integration_id=integration_id,
            entity_type="product",
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Publish ProductSyncRequested event for the specific integration
    _settings = _get_settings()
    _publisher = EventPublisher(
        kafka_bootstrap_servers=_settings.kafka_bootstrap_servers
    )
    _sync_event = ProductSyncRequested(
        integration_id=integration_id,
        full_sync=True,
        triggered_by="manual",
        job_id=job.id,
    )
    try:
        await _publisher.publish(
            topic="sync.requested", event=_sync_event, route_by_type=True
        )
    except Exception as e:
        logger.error(
            "sync_event_publish_failed",
            integration_id=str(integration_id),
            error=str(e),
        )
        raise HTTPException(
            status_code=503,
            detail="Sync job created but event dispatch failed. The job will be retried.",
        )
    finally:
        await _publisher.close()

    return SyncJobResponse.model_validate(job)


@router.get("/{shop_id}/sync/status", response_model=SyncStatusResponse)
async def get_sync_status(
    shop_id: UUID,
    integration_id: UUID = Query(...),
    entity_type: str = Query("product", pattern="^(product|inventory|order)$"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get sync status for integration."""
    await verify_shop_ownership(shop_id, current_user, session)

    service = SyncService(session)
    return await service.get_sync_status_by_integration(integration_id, entity_type)
