"""
Integration Service
===================
Business logic for shop platform integrations

Includes automatic webhook registration on connect and cleanup on disconnect.
"""

import asyncio
import json
import structlog
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from urllib.parse import quote
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from ..repository import (
    ShopRepository,
    ShopIntegrationRepository,
    PlatformRepository,
)
from ..models import Shop, ShopIntegration, Platform


logger = structlog.get_logger(__name__)


# Webhook events to subscribe per platform (Basalam uses numeric event_ids)
PLATFORM_WEBHOOK_EVENTS = {
    "basalam": [8, 5, 7],  # 8=PRODUCT_CREATE_CHANGES, 5=VENDOR_NEW_ORDER, 7=VENDOR_PARCEL_CHANGES
}


class WebhookRegistrationError(Exception):
    """Raised when webhook registration with platform fails"""
    pass


class IntegrationService:
    """
    Service for managing shop platform integrations.

    Handles connecting, disconnecting, and testing platform integrations.
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize service with database session.

        Args:
            session: Async SQLAlchemy session for database operations
        """
        self.session = session
        self._shop_repository = ShopRepository(session)
        self._integration_repository = ShopIntegrationRepository(session)
        self._platform_repository = PlatformRepository(session)

    async def _get_shop_or_fail(self, shop_id: uuid.UUID) -> Shop:
        """
        Get shop by ID or raise ValueError if not found.

        Args:
            shop_id: UUID of the shop

        Returns:
            Shop instance

        Raises:
            ValueError: If shop not found
        """
        shop = await self._shop_repository.get_by_id(shop_id)
        if not shop:
            raise ValueError(f"Shop with id '{shop_id}' not found")
        return shop

    async def _get_platform_or_fail(self, platform_code: str) -> Platform:
        """
        Get platform by code or raise ValueError if not found.

        Args:
            platform_code: Platform code (e.g., 'basalam', 'shopify')

        Returns:
            Platform instance

        Raises:
            ValueError: If platform not found
        """
        platform = await self._platform_repository.get_by_code(platform_code)
        if not platform:
            raise ValueError(f"Platform with code '{platform_code}' not found")
        return platform

    async def connect_shop(
        self,
        shop_id: uuid.UUID,
        platform_code: str,
        credentials: Dict[str, Any],
        register_webhooks: bool = True,
    ) -> ShopIntegration:
        """
        Connect shop to a platform.

        Args:
            shop_id: UUID of the shop
            platform_code: Platform code (e.g., 'basalam', 'shopify')
            credentials: Dictionary containing connection credentials
            register_webhooks: Whether to automatically register webhooks (default: True)

        Returns:
            Newly created ShopIntegration instance

        Raises:
            ValueError: If shop or platform not found
            WebhookRegistrationError: If webhook registration fails
        """
        shop = await self._get_shop_or_fail(shop_id)
        platform = await self._get_platform_or_fail(platform_code)

        integration_data = {
            "shop_id": shop.id,
            "platform_id": platform.id,
            "connection_type": credentials.get("connection_type", "api"),
            "credentials_encrypted": credentials.get("credentials"),
            "external_shop_id": credentials.get("external_shop_id"),
            "status": "pending",  # Start as pending, will be connected after webhook registration
            "webhook_status": "not_registered",
        }

        # Create integration first
        integration = await self._integration_repository.create(integration_data)

        if register_webhooks:
            try:
                # Register webhooks with the platform
                webhook_result = await self._register_webhook_with_platform(
                    integration=integration,
                    platform=platform,
                )

                # Update integration with webhook details
                update_data = {
                    "webhook_id": webhook_result.get("webhook_id"),
                    "webhook_status": "active",
                    "webhook_registered_at": datetime.now(timezone.utc),
                    "status": "connected",
                }
                integration = await self._integration_repository.update(
                    integration.id, update_data
                )
                logger.info(
                    "webhooks_registered",
                    integration_id=str(integration.id),
                )

            except Exception as e:
                # Webhook registration failed — UnitOfWork will roll back the integration creation
                logger.error("webhook_registration_failed", error=str(e))
                raise WebhookRegistrationError(
                    f"Failed to register webhooks with {platform_code}: {str(e)}"
                ) from e
        else:
            # No webhook registration - mark as connected
            integration = await self._integration_repository.update_status(
                integration.id, "connected"
            )

        return integration

    async def _register_webhook_with_platform(
        self,
        integration: ShopIntegration,
        platform: Platform,
    ) -> Dict[str, Any]:
        """
        Register webhooks with external platform using 2-step flow for Basalam.

        For Basalam specifically:
        1. Create webhook with numeric event_ids via BasalamClient
        2. Subscribe vendor using their own access token

        Args:
            integration: The ShopIntegration instance
            platform: The Platform instance

        Returns:
            Dict containing webhook_id and other platform-specific data

        Raises:
            WebhookRegistrationError: If registration fails
        """
        from src.core.config import get_settings
        from src.domains.shops.service.webhook_secret_service import get_webhook_secret_service

        settings = get_settings()
        secret_service = get_webhook_secret_service()

        # Generate webhook secret
        secret = secret_service.generate_secret()
        encrypted_secret = secret_service.encrypt_for_storage(secret)

        # Build webhook URL using configured base URL
        base_url = settings.webhook_base_url or settings.base_url
        webhook_url = f"{base_url}/api/v1/webhooks/{platform.code}/{integration.id}"

        # Get events to subscribe — numeric IDs for Basalam
        events = PLATFORM_WEBHOOK_EVENTS.get(platform.code, [])

        if platform.code == "basalam":
            return await self._register_basalam_webhook(
                integration=integration,
                webhook_url=webhook_url,
                events=events,
                encrypted_secret=encrypted_secret,
            )

        # Non-Basalam platforms (Shopify, WooCommerce) — delegate to connector
        from src.integrations.shop.registry import get_connector
        from src.integrations.shop.ports import ShopConnectorPort

        connector: ShopConnectorPort = get_connector(
            platform.code,
            {"credentials": integration.credentials_encrypted},
            vendor_id=integration.external_shop_id,
        )

        try:
            success = await connector.register_webhook(webhook_url, events)

            await self._integration_repository.update(
                integration.id,
                {"webhook_secret_encrypted": encrypted_secret},
            )

            logger.info(
                "webhook_registered_with_events",
                integration_id=str(integration.id),
                events=events,
                success=success,
            )

            return {
                "webhook_id": str(integration.id),  # fallback ID when platform doesn't return one
                "webhook_url": webhook_url,
                "events": events,
                "success": success,
            }

        except Exception as e:
            logger.error(
                "webhook_registration_platform_failed",
                platform=platform.code,
                error=str(e),
                integration_id=str(integration.id),
            )
            raise

    async def _register_basalam_webhook(
        self,
        integration: ShopIntegration,
        webhook_url: str,
        events: list,
        encrypted_secret: str,
    ) -> Dict[str, Any]:
        """2-step Basalam webhook registration: create webhook then subscribe vendor."""
        from src.core.config import get_settings
        from src.domains.shops.service.webhook_secret_service import get_webhook_secret_service
        from src.integrations.basalam.client import BasalamClient

        settings = get_settings()

        # Decrypt credentials to get vendor access token
        secret_service = get_webhook_secret_service()
        credentials_blob = integration.credentials_encrypted
        if isinstance(credentials_blob, dict):
            encrypted = credentials_blob.get("encrypted", "")
        else:
            encrypted = str(credentials_blob)

        decrypted = secret_service.decrypt_from_storage(encrypted)
        creds = json.loads(decrypted)
        access_token = creds.get("access_token", "")
        refresh_token = creds.get("refresh_token", "")

        client = BasalamClient(
            client_id=settings.basalam_client_id,
            client_secret=settings.basalam_client_secret.get_secret_value(),
            access_token=access_token,
            refresh_token=refresh_token,
        )

        try:
            # Step 1: Create webhook with numeric event_ids
            result = await client.register_webhook(
                url=webhook_url,
                events=events,  # numeric IDs like [8, 5, 7]
            )
            webhook_id = str(result.get("id", result.get("webhook_id", "")))

            # Step 2: Subscribe vendor to the webhook with their own token
            await client.subscribe_user_to_webhook(
                webhook_id=webhook_id,
                access_token=access_token,
            )

            # Store encrypted webhook secret and webhook_id
            await self._integration_repository.update(
                integration.id,
                {
                    "webhook_secret_encrypted": encrypted_secret,
                    "webhook_id": webhook_id,
                },
            )

            logger.info(
                "basalam_webhook_registered",
                webhook_id=webhook_id,
                integration_id=str(integration.id),
                events=events,
            )

            return {
                "webhook_id": webhook_id,
                "webhook_url": webhook_url,
                "events": events,
            }

        except Exception as e:
            logger.error(
                "basalam_webhook_registration_failed",
                integration_id=str(integration.id),
                error=str(e),
                exc_info=True,
            )
            raise

        finally:
            await client.close()

    async def disconnect_shop(
        self,
        shop_id: uuid.UUID,
        platform_id: uuid.UUID,
        cleanup_webhooks: bool = True,
    ) -> bool:
        """
        Disconnect a shop integration.

        Args:
            shop_id: UUID of the shop
            platform_id: UUID of the platform
            cleanup_webhooks: Whether to unregister webhooks (default: True)

        Returns:
            True if disconnected successfully

        Raises:
            ValueError: If integration not found
        """
        integrations = await self._integration_repository.get_by_shop(shop_id)
        integration = next(
            (i for i in integrations if i.platform_id == platform_id), None
        )

        if not integration:
            raise ValueError(
                f"Integration not found for shop '{shop_id}' and platform '{platform_id}'"
            )

        # Unregister webhooks if requested and they exist
        if cleanup_webhooks and integration.webhook_id:
            try:
                await self._unregister_webhook_from_platform(integration)
                webhook_status = "inactive"
            except Exception as e:
                logger.warning(
                    "webhook_unregister_failed",
                    integration_id=str(integration.id),
                    error=str(e),
                )
                webhook_status = "cleanup_failed"
        else:
            webhook_status = integration.webhook_status

        # Update integration status
        await self._integration_repository.update(
            integration.id,
            {
                "status": "disconnected",
                "webhook_status": webhook_status,
            },
        )
        return True

    async def _unregister_webhook_from_platform(
        self,
        integration: ShopIntegration,
    ) -> bool:
        """
        Unregister webhooks from external platform.

        Args:
            integration: The ShopIntegration instance

        Returns:
            True if unregistered successfully

        Raises:
            Exception: If unregistration fails
        """
        from src.integrations.shop.registry import get_connector

        if not integration.webhook_id:
            logger.info("no_webhook_to_unregister", integration_id=str(integration.id))
            return True

        # Get platform
        platform = await self._platform_repository.get_by_id(integration.platform_id)
        if not platform:
            raise ValueError(f"Platform not found for integration {integration.id}")

        # Get platform connector
        connector = get_connector(
            platform.code,
            {"credentials": integration.credentials_encrypted},
            vendor_id=integration.external_shop_id,
        )

        # Unregister webhook
        await connector.unregister_webhook(integration.webhook_id)

        logger.info(
            "webhook_unregistered",
            webhook_id=integration.webhook_id,
            integration_id=str(integration.id),
        )
        return True

    async def get_integration(
        self, shop_id: uuid.UUID, platform_id: uuid.UUID
    ) -> Optional[ShopIntegration]:
        """
        Get integration for a specific shop and platform.

        Args:
            shop_id: UUID of the shop
            platform_id: UUID of the platform

        Returns:
            ShopIntegration instance if found, None otherwise
        """
        integrations = await self._integration_repository.get_by_shop(shop_id)
        return next((i for i in integrations if i.platform_id == platform_id), None)

    async def list_integrations(self, shop_id: uuid.UUID) -> List[ShopIntegration]:
        """
        List all integrations for a shop.

        Args:
            shop_id: UUID of the shop

        Returns:
            List of ShopIntegration instances
        """
        return await self._integration_repository.get_by_shop(shop_id)

    async def refresh_token(
        self, shop_id: uuid.UUID, platform_id: uuid.UUID
    ) -> Optional[ShopIntegration]:
        """
        Refresh OAuth token for an integration with Redis distributed lock.

        Uses a Redis lock (``oauth:refresh:{integration_id}``, 30s TTL) to prevent
        concurrent refresh race conditions.

        Args:
            shop_id: UUID of the shop
            platform_id: UUID of the platform

        Returns:
            Updated ShopIntegration instance

        Raises:
            ValueError: If integration not found or not OAuth type
        """
        from src.core.redis_client import get_redis_client
        from src.core.config import get_settings
        from src.integrations.basalam.client import BasalamClient

        integration = await self.get_integration(shop_id, platform_id)

        if not integration:
            raise ValueError(
                f"Integration not found for shop '{shop_id}' and platform '{platform_id}'"
            )

        if integration.connection_type != "oauth":
            raise ValueError("Only OAuth integrations support token refresh")

        # Redis distributed lock to prevent concurrent refresh race
        lock_key = f"oauth:refresh:{integration.id}"
        redis_client = get_redis_client()
        lock_acquired = await redis_client.set(
            lock_key, "1", nx=True, ex=30
        )

        if not lock_acquired:
            logger.info(
                "token_refresh_already_in_progress",
                integration_id=str(integration.id),
            )
            # Wait briefly and return current state
            await asyncio.sleep(2)
            return await self._integration_repository.get_by_id(integration.id)

        try:
            # Decrypt current credentials to get refresh_token
            credentials = integration.credentials_encrypted or {}
            if isinstance(credentials, dict) and "encrypted" in credentials:
                from src.domains.shops.service.webhook_secret_service import get_webhook_secret_service
                secret_service = get_webhook_secret_service()
                decrypted = secret_service.decrypt_from_storage(credentials["encrypted"])
                creds = json.loads(decrypted)
            else:
                creds = credentials

            refresh_token_val = creds.get("refresh_token", "")
            if not refresh_token_val:
                raise ValueError("No refresh token available for integration")

            # Create client and refresh
            settings = get_settings()
            client = BasalamClient(
                client_id=settings.basalam_client_id,
                client_secret=settings.basalam_client_secret.get_secret_value(),
            )

            try:
                token_data = await client.refresh_access_token_with_code(
                    refresh_token_val
                )
            except Exception as e:
                logger.error(
                    "token_refresh_failed",
                    integration_id=str(integration.id),
                    error=str(e),
                )
                # If refresh fails with auth error, mark as disconnected
                await self._integration_repository.update(
                    integration.id,
                    {"status": "disconnected", "last_error": f"Token refresh failed: {e}"},
                )
                raise

            # Re-encrypt and store new credentials
            new_creds = {
                "access_token": token_data.get("access_token", ""),
                "refresh_token": token_data.get(
                    "refresh_token", refresh_token_val
                ),
                "vendor_id": creds.get("vendor_id", ""),
            }
            from src.domains.shops.service.webhook_secret_service import (
                get_webhook_secret_service,
            )
            secret_service = get_webhook_secret_service()
            encrypted = secret_service.encrypt_for_storage(
                json.dumps(new_creds)
            )

            integration = await self._integration_repository.update(
                integration.id,
                {
                    "credentials_encrypted": {"encrypted": encrypted},
                    "status": "connected",
                    "last_error": None,
                },
            )

            logger.info("token_refreshed", integration_id=str(integration.id))
            return integration

        finally:
            # Always release the lock
            await redis_client.delete(lock_key)
            await client.close()

    async def test_connection(
        self, shop_id: uuid.UUID, platform_id: uuid.UUID
    ) -> Dict[str, Any]:
        """
        Test connection status for an integration.

        Args:
            shop_id: UUID of the shop
            platform_id: UUID of the platform

        Returns:
            Dictionary with connection test results

        Raises:
            ValueError: If integration not found
        """
        integration = await self.get_integration(shop_id, platform_id)

        if not integration:
            raise ValueError(
                f"Integration not found for shop '{shop_id}' and platform '{platform_id}'"
            )

        return {
            "connected": integration.status == "connected",
            "status": integration.status,
            "last_error": integration.last_error,
            "last_synced_at": integration.last_synced_at,
        }

    async def deactivate_on_auth_failure(
        self, integration_id: uuid.UUID, error_message: str = "Authentication failed"
    ) -> None:
        """
        Mark integration as disconnected when a 401 auth error is encountered.

        Called by sync services and webhook processors when they receive
        authentication errors from the platform API.

        Args:
            integration_id: UUID of the integration to deactivate
            error_message: Description of the auth failure
        """
        logger.warning(
            "deactivating_integration_auth_error",
            integration_id=str(integration_id),
            error=error_message,
        )
        await self._integration_repository.update(
            integration_id,
            {"status": "disconnected", "last_error": error_message},
        )

    async def start_oauth(
        self, shop_id: uuid.UUID, platform_code: str
    ) -> Dict[str, Any]:
        """
        Start OAuth 2.0 flow for a shop platform integration.

        Generates a real authorization URL, stores CSRF state in Redis,
        creates a pending integration record.

        Args:
            shop_id: UUID of the shop
            platform_code: Platform code (e.g., 'basalam')

        Returns:
            Dict with authorize_url, state, integration_id

        Raises:
            ValueError: If shop or platform not found
        """
        from src.core.config import get_settings
        from src.core.redis_client import get_redis_client
        from src.integrations.shop.registry import get_connector as get_shop_connector

        shop = await self._get_shop_or_fail(shop_id)
        platform = await self._get_platform_or_fail(platform_code)
        settings = get_settings()

        # Generate random state for CSRF protection
        state = uuid.uuid4().hex

        # Build authorization URL from connector's OAuth config (single source of truth)
        connector = get_shop_connector(platform_code)
        oauth_cfg = connector.oauth_config
        redirect_uri = f"{settings.base_url}/api/v1/shops/{shop_id}/oauth/callback"
        scope = "+".join(oauth_cfg.scopes)

        authorize_url = (
            f"{oauth_cfg.authorize_url}?"
            f"client_id={oauth_cfg.client_id}"
            f"&scope={quote(scope)}"
            f"&redirect_uri={quote(redirect_uri, safe='')}"
            f"&state={state}"
            f"&response_type=code"
        )

        # Store state in Redis with 10-min TTL (includes platform_code for callback)
        redis_client = get_redis_client()
        await redis_client.setex(
            f"oauth:state:{state}",
            600,
            json.dumps({
                "shop_id": str(shop_id),
                "platform_code": platform_code,
            }),
        )

        # Create pending integration
        integration_data = {
            "shop_id": shop.id,
            "platform_id": platform.id,
            "connection_type": "oauth",
            "status": "pending",
            "webhook_status": "not_registered",
        }
        integration = await self._integration_repository.create(integration_data)

        logger.info(
            "oauth_flow_started",
            shop_id=str(shop_id),
            platform_code=platform_code,
            integration_id=str(integration.id),
        )

        return {
            "authorize_url": authorize_url,
            "state": state,
            "integration_id": integration.id,
        }

    async def handle_oauth_callback(
        self, shop_id: uuid.UUID, code: str, state: str
    ) -> ShopIntegration:
        """
        Handle OAuth callback — exchange code for tokens, fetch vendor identity.

        Verifies state from Redis, exchanges authorization code for tokens,
        fetches vendor info from Basalam, encrypts and stores credentials.

        Args:
            shop_id: UUID of the shop
            code: OAuth authorization code from the provider
            state: CSRF state parameter from the authorization URL

        Returns:
            Updated ShopIntegration instance

        Raises:
            ValueError: If state is invalid, code exchange fails, or no vendor found
        """
        from src.core.config import get_settings
        from src.core.redis_client import get_redis_client
        from src.integrations.basalam.client import BasalamClient
        from src.domains.shops.service.webhook_secret_service import (
            get_webhook_secret_service,
        )

        settings = get_settings()
        redis_client = get_redis_client()

        # Verify state from Redis
        stored_data = await redis_client.get(f"oauth:state:{state}")
        if not stored_data:
            raise ValueError("Invalid or expired OAuth state")

        # Clean up state
        await redis_client.delete(f"oauth:state:{state}")

        state_payload = json.loads(stored_data)
        if state_payload.get("shop_id") != str(shop_id):
            raise ValueError("OAuth state does not match shop")

        platform_code = state_payload.get("platform_code")
        platform = await self._get_platform_or_fail(platform_code)
        shop = await self._get_shop_or_fail(shop_id)

        # Find the pending integration for this shop/platform
        integrations = await self._integration_repository.get_by_shop(shop_id)
        integration = next(
            (
                i
                for i in integrations
                if i.platform_id == platform.id
                and i.status == "pending"
                and i.connection_type == "oauth"
            ),
            None,
        )
        if not integration:
            raise ValueError(
                "No pending OAuth integration found for this shop and platform"
            )

        # Exchange authorization code for tokens
        redirect_uri = f"{settings.base_url}/api/v1/shops/{shop_id}/oauth/callback"
        client = BasalamClient(
            client_id=settings.basalam_client_id,
            client_secret=settings.basalam_client_secret.get_secret_value(),
        )

        try:
            token_data = await client.exchange_authorization_code(code, redirect_uri)
        except Exception as e:
            logger.error("token_exchange_failed", integration_id=str(integration.id), error=str(e))
            raise ValueError(
                f"Failed to exchange authorization code with Basalam: {e}"
            )

        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")

        # Fetch current user to get vendor_id
        try:
            user_data = await client.get_current_user(access_token)
        except Exception as e:
            logger.error("user_info_fetch_failed", integration_id=str(integration.id), error=str(e))
            raise ValueError(f"Failed to fetch user info from Basalam: {e}")

        vendor_info = user_data.get("vendor")
        if not vendor_info or not vendor_info.get("id"):
            raise ValueError("No Basalam vendor account found for this user")

        vendor_id = str(vendor_info["id"])

        # Check if this vendor_id is already connected to a different shop
        existing = await self._integration_repository.get_by_platform_shop(
            platform.id, vendor_id
        )
        if existing and existing.shop_id != shop_id:
            await client.close()
            raise ValueError(
                f"This Basalam vendor account (ID: {vendor_id}) is already "
                f"connected to another shop. Disconnect it first."
            )

        # Encrypt credentials with Fernet
        secret_service = get_webhook_secret_service()
        credentials_blob = json.dumps({
            "access_token": access_token,
            "refresh_token": refresh_token,
            "vendor_id": vendor_id,
        })
        encrypted_credentials = secret_service.encrypt_for_storage(credentials_blob)

        # Update integration with encrypted tokens and vendor info
        integration = await self._integration_repository.update(
            integration.id,
            {
                "credentials_encrypted": {"encrypted": encrypted_credentials},
                "external_shop_id": vendor_id,
                "status": "connected",
            },
        )

        # Register webhooks with the platform (non-blocking failure)
        try:
            webhook_result = await self._register_webhook_with_platform(
                integration=integration, platform=platform,
            )
            await self._integration_repository.update(integration.id, {
                "webhook_id": webhook_result.get("webhook_id"),
                "webhook_status": "active",
                "webhook_registered_at": datetime.now(timezone.utc),
            })
            logger.info("webhooks_registered_after_oauth",
                        integration_id=str(integration.id),
                        webhook_id=webhook_result.get("webhook_id"))
        except Exception as e:
            logger.warning("webhook_registration_failed_after_oauth",
                           integration_id=str(integration.id), error=str(e))
            await self._integration_repository.update(integration.id,
                {"webhook_status": "not_registered"})

        # Update shop settings with vendor metadata
        shop_settings = shop.settings or {}
        shop_settings.update({
            "basalam_shop_name": vendor_info.get("title", ""),
            "basalam_shop_identifier": vendor_info.get("identifier", ""),
            "basalam_connected_at": datetime.now(timezone.utc).isoformat(),
        })
        await self._shop_repository.update(shop.id, {"settings": shop_settings})

        logger.info(
            "basalam_vendor_connected",
            vendor_id=vendor_id,
            integration_id=str(integration.id),
        )

        await client.close()
        return integration

    async def rotate_webhook_secret(
        self,
        integration_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """
        Rotate webhook secret for an integration.

        During rotation, both old and new secrets are valid for 24 hours.
        The platform is updated with the new secret.

        Args:
            integration_id: UUID of the integration

        Returns:
            Dict with rotation details including new_secret_plaintext (store securely!)

        Raises:
            ValueError: If integration not found or not active
        """
        from src.domains.shops.service.webhook_secret_service import get_webhook_secret_service
        from src.integrations.shop.registry import get_connector
        from src.core.config import get_settings

        integration = await self._integration_repository.get_by_id(integration_id)
        if not integration:
            raise ValueError(f"Integration '{integration_id}' not found")

        if integration.status != "connected":
            raise ValueError(
                f"Cannot rotate secret for disconnected integration (status: {integration.status})"
            )

        secret_service = get_webhook_secret_service()
        settings = get_settings()

        # Generate new secret
        (
            new_secret_plaintext,
            new_secret_encrypted,
            old_secret_expires_at,
        ) = secret_service.rotate_secret(integration.webhook_secret_encrypted)

        # Get platform connector
        platform = await self._platform_repository.get_by_id(integration.platform_id)
        if not platform:
            raise ValueError(f"Platform not found for integration {integration.id}")

        connector = get_connector(
            platform.code,
            {"credentials": integration.credentials_encrypted},
            vendor_id=integration.external_shop_id,
        )

        try:
            # Update platform with new secret
            base_url = settings.webhook_base_url or settings.base_url
            webhook_url = f"{base_url}/api/v1/webhooks/{platform.code}/{integration.id}"

            # Update webhook on platform
            await connector.update_webhook(
                integration.webhook_id,
                {"secret": new_secret_plaintext, "url": webhook_url},
            )

            # Store new encrypted secret
            await self._integration_repository.update(
                integration.id,
                {
                    "webhook_secret_encrypted": new_secret_encrypted,
                    "webhook_previous_secret_encrypted": integration.webhook_secret_encrypted,
                    "webhook_secret_rotated_at": datetime.now(timezone.utc),
                    "webhook_previous_secret_expires_at": old_secret_expires_at,
                },
            )

            logger.info(
                "webhook_secret_rotated",
                integration_id=str(integration.id),
                previous_secret_expires_at=str(old_secret_expires_at),
            )

            return {
                "integration_id": str(integration.id),
                "new_secret": new_secret_plaintext,  # Only returned once!
                "previous_secret_expires_at": old_secret_expires_at.isoformat(),
                "message": "Store the new_secret securely. Previous secret remains valid for 24 hours.",
            }

        except Exception as e:
            logger.error(
                "webhook_secret_rotation_failed",
                integration_id=str(integration.id),
                error=str(e),
            )
            raise WebhookRegistrationError(
                f"Failed to update platform with new secret: {str(e)}"
            ) from e

    async def get_webhook_status(
        self,
        integration_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """
        Get webhook status for an integration.

        Args:
            integration_id: UUID of the integration

        Returns:
            Dict with webhook status details

        Raises:
            ValueError: If integration not found
        """
        integration = await self._integration_repository.get_by_id(integration_id)
        if not integration:
            raise ValueError(f"Integration '{integration_id}' not found")

        # Count recent webhooks
        from sqlalchemy import text
        result = await self.session.execute(text("""
            SELECT
                COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '24 hours') as last_24h,
                COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '7 days') as last_7d,
                COUNT(*) FILTER (WHERE status = 'completed') as total_processed,
                COUNT(*) FILTER (WHERE status = 'failed') as total_failed,
                MAX(created_at) FILTER (WHERE status = 'completed') as last_processed_at,
                MAX(created_at) as last_received_at
            FROM webhook_events
            WHERE integration_id = :integration_id
        """), {"integration_id": str(integration_id)})
        stats = result.fetchone()

        return {
            "integration_id": str(integration.id),
            "webhook_status": integration.webhook_status,
            "webhook_id": integration.webhook_id,
            "webhook_registered_at": (
                integration.webhook_registered_at.isoformat()
                if integration.webhook_registered_at else None
            ),
            "webhooks_received_24h": stats[0] or 0,
            "webhooks_received_7d": stats[1] or 0,
            "webhooks_processed_total": stats[2] or 0,
            "webhooks_failed_total": stats[3] or 0,
            "last_processed_at": str(stats[4]) if stats[4] else None,
            "last_received_at": str(stats[5]) if stats[5] else None,
        }
