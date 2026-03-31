"""
Shop Service
============
Business logic for shop management
"""

from typing import List, Optional, Dict, Any
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from ..repository import ShopRepository
from ..models import Shop


VALID_ROLES = {"supplier", "seller"}


class ShopService:
    """
    Service for managing shop business logic.

    Handles shop creation, retrieval, updates, and role validation.
    A shop can only have ONE role: 'supplier' OR 'seller' (not both).
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize service with database session.

        Args:
            session: Async SQLAlchemy session for database operations
        """
        self.session = session
        self._repository = ShopRepository(session)

    def validate_role(self, role: str) -> bool:
        """
        Validate that role is either 'supplier' OR 'seller'.

        Args:
            role: Role string to validate

        Returns:
            True if role is valid, False otherwise
        """
        return role in VALID_ROLES

    async def create_shop(self, account_id: uuid.UUID, name: str, role: str) -> Shop:
        """
        Create a new shop with role validation.

        Args:
            account_id: UUID of the account owning the shop
            name: Shop name
            role: Shop role - must be 'supplier' OR 'seller' only

        Returns:
            Newly created Shop instance

        Raises:
            ValueError: If role is not 'supplier' or 'seller'
        """
        if not self.validate_role(role):
            raise ValueError(
                f"Invalid role '{role}'. Must be one of: {', '.join(VALID_ROLES)}"
            )

        shop_data = {
            "account_id": account_id,
            "name": name,
            "shop_role": role,
            "status": "active",
            "settings": {},
        }

        return await self._repository.create(shop_data)

    async def get_shop(self, shop_id: uuid.UUID) -> Optional[Shop]:
        """
        Get shop by ID.

        Args:
            shop_id: UUID of the shop

        Returns:
            Shop instance if found, None otherwise
        """
        return await self._repository.get_by_id(shop_id)

    async def list_shops_by_account(self, account_id: uuid.UUID) -> List[Shop]:
        """
        List all shops for a specific account.

        Args:
            account_id: UUID of the account

        Returns:
            List of Shop instances belonging to the account
        """
        return await self._repository.get_by_account(account_id)

    async def list_suppliers(self) -> List[Shop]:
        """
        List all supplier shops.

        Returns:
            List of all Shop instances with role 'supplier'
        """
        return await self._repository.get_by_role_global("supplier")

    async def list_sellers(self) -> List[Shop]:
        """
        List all seller shops.

        Returns:
            List of all Shop instances with role 'seller'
        """
        return await self._repository.get_by_role_global("seller")

    async def update_shop(
        self, shop_id: uuid.UUID, data: Dict[str, Any]
    ) -> Optional[Shop]:
        """
        Update shop fields.

        Args:
            shop_id: UUID of the shop
            data: Dictionary containing fields to update

        Returns:
            Updated Shop instance if found, None otherwise

        Raises:
            ValueError: If attempting to set invalid role
        """
        if "shop_role" in data and not self.validate_role(data["shop_role"]):
            raise ValueError(
                f"Invalid role '{data['shop_role']}'. Must be one of: {', '.join(VALID_ROLES)}"
            )

        return await self._repository.update(shop_id, data)

    async def disable_shop(self, shop_id: uuid.UUID) -> bool:
        """
        Disable shop (soft delete).

        Sets shop status to 'disabled'.

        Args:
            shop_id: UUID of the shop

        Returns:
            True if shop was disabled, False if not found
        """
        return await self._repository.delete(shop_id)
