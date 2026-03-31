"""
Integration Service
===================
Business logic for shop platform integrations

Includes automatic webhook registration on connect and cleanup on disconnect.
"""

import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from ..repository import (
    ShopRepository,
    ShopIntegrationRepository,
    PlatformRepository,
)
from ..models import Shop, ShopIntegration, Platform


logger = logging.getLogger(__name__)


# Webhook events to subscribe per platform
PLATFORM_WEBHOOK_EVENTS = {
    "basalam": ["order.created", "order.updated", "inventory.updated", "product.updated"],
    "shopify": ["orders/create", "orders/updated", "inventory_levels/update", "products/update"],
    "woocommerce": ["order.created", "order.updated", "product.updated"],
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
                    "webhook_registered_at": datetime.utcnow(),
                    "status": "connected",
                }
                integration = await self._integration_repository.update(
                    integration.id, update_data
                )
                logger.info(
                    f"Successfully registered webhooks for integration {integration.id}"
                )

            except Exception as e:
                # Webhook registration failed - delete integration and raise error
                logger.error(f"Webhook registration failed: {e}")
                await self._integration_repository.delete(integration.id)

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
        Register webhooks with external platform.

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
        from src.integrations.shop.connector import get_connector
        from src.integrations.shop.connector import ShopConnector

        settings = get_settings()
        secret_service = get_webhook_secret_service()

        # Generate webhook secret
        secret = secret_service.generate_secret()
        encrypted_secret = secret_service.encrypt_for_storage(secret)

        # Build webhook URL
        base_url = settings.webhook_base_url or settings.base_url
        webhook_url = f"{base_url}/api/v1/webhooks/{platform.code}/{integration.id}"

        # Get events to subscribe
        events = PLATFORM_WEBHOOK_EVENTS.get(platform.code, ["*"])

        # Get platform connector
        connector: ShopConnector = get_connector(platform.code, {
            "credentials": integration.credentials_encrypted,
        })

        try:
            # Call platform's register_webhook
            webhook_id = await connector.register_webhook(webhook_url, events)

            # Store encrypted secret
            await self._integration_repository.update(
                integration.id,
                {"webhook_secret_encrypted": encrypted_secret},
            )

            logger.info(
                f"Registered webhook {webhook_id} for integration {integration.id} "
                f"with events: {events}"
            )

            return {
                "webhook_id": webhook_id,
                "webhook_url": webhook_url,
                "events": events,
            }

        except Exception as e:
            logger.error(
                f"Failed to register webhook with {platform.code}: {e}",
                extra={"integration_id": str(integration.id)},
            )
            raise

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
                    f"Failed to unregister webhooks for integration {integration.id}: {e}"
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
        from src.integrations.shop.connector import get_connector

        if not integration.webhook_id:
            logger.info(f"No webhook to unregister for integration {integration.id}")
            return True

        # Get platform
        platform = await self._platform_repository.get_by_id(integration.platform_id)
        if not platform:
            raise ValueError(f"Platform not found for integration {integration.id}")

        # Get platform connector
        connector = get_connector(platform.code, {
            "credentials": integration.credentials_encrypted,
        })

        # Unregister webhook
        await connector.unregister_webhook(integration.webhook_id)

        logger.info(
            f"Unregistered webhook {integration.webhook_id} for integration {integration.id}"
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
        Refresh OAuth token for an integration.

        Args:
            shop_id: UUID of the shop
            platform_id: UUID of the platform

        Returns:
            Updated ShopIntegration instance

        Raises:
            ValueError: If integration not found or not OAuth type
        """
        integration = await self.get_integration(shop_id, platform_id)

        if not integration:
            raise ValueError(
                f"Integration not found for shop '{shop_id}' and platform '{platform_id}'"
            )

        if integration.connection_type != "oauth":
            raise ValueError("Only OAuth integrations support token refresh")

        return await self._integration_repository.update_status(
            integration.id, "connected"
        )

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

    async def handle_oauth_callback(
        self, shop_id: uuid.UUID, platform_code: str, code: str
    ) -> ShopIntegration:
        """
        Handle OAuth callback and create integration.

        Args:
            shop_id: UUID of the shop
            platform_code: Platform code (e.g., 'basalam', 'shopify')
            code: OAuth authorization code

        Returns:
            Newly created ShopIntegration instance

        Raises:
            ValueError: If shop or platform not found
        """
        shop = await self._get_shop_or_fail(shop_id)
        platform = await self._get_platform_or_fail(platform_code)

        credentials = {
            "connection_type": "oauth",
            "credentials": {"auth_code": code},
        }

        integration_data = {
            "shop_id": shop.id,
            "platform_id": platform.id,
            "connection_type": "oauth",
            "credentials_encrypted": credentials["credentials"],
            "status": "connected",
        }

        return await self._integration_repository.create(integration_data)

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
        from src.integrations.shop.connector import get_connector
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

        connector = get_connector(platform.code, {
            "credentials": integration.credentials_encrypted,
        })

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
                    "webhook_secret_rotated_at": datetime.utcnow(),
                    "webhook_previous_secret_expires_at": old_secret_expires_at,
                },
            )

            logger.info(
                f"Rotated webhook secret for integration {integration.id}. "
                f"Previous secret expires at {old_secret_expires_at}"
            )

            return {
                "integration_id": str(integration.id),
                "new_secret": new_secret_plaintext,  # Only returned once!
                "previous_secret_expires_at": old_secret_expires_at.isoformat(),
                "message": "Store the new_secret securely. Previous secret remains valid for 24 hours.",
            }

        except Exception as e:
            logger.error(
                f"Failed to rotate webhook secret for integration {integration.id}: {e}"
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
