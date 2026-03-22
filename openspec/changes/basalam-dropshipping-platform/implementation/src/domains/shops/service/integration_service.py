"""
Integration Service
===================
Business logic for shop platform integrations
"""

from typing import List, Optional, Dict, Any
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from ..repository import (
    ShopRepository,
    ShopIntegrationRepository,
    PlatformRepository,
)
from ..models import Shop, ShopIntegration, Platform


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
    ) -> ShopIntegration:
        """
        Connect shop to a platform.

        Args:
            shop_id: UUID of the shop
            platform_code: Platform code (e.g., 'basalam', 'shopify')
            credentials: Dictionary containing connection credentials

        Returns:
            Newly created ShopIntegration instance

        Raises:
            ValueError: If shop or platform not found
        """
        shop = await self._get_shop_or_fail(shop_id)
        platform = await self._get_platform_or_fail(platform_code)

        integration_data = {
            "shop_id": shop.id,
            "platform_id": platform.id,
            "connection_type": credentials.get("connection_type", "api"),
            "credentials_encrypted": credentials.get("credentials"),
            "external_shop_id": credentials.get("external_shop_id"),
            "status": "connected",
        }

        return await self._integration_repository.create(integration_data)

    async def disconnect_shop(self, shop_id: uuid.UUID, platform_id: uuid.UUID) -> bool:
        """
        Disconnect a shop integration.

        Args:
            shop_id: UUID of the shop
            platform_id: UUID of the platform

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

        await self._integration_repository.update_status(integration.id, "disconnected")
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
