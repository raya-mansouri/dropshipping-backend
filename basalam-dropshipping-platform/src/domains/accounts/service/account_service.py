"""
Account Service
===============
Service layer for account management operations
"""

import uuid
from typing import Optional, List, Dict, Any

from ..repository import AccountRepository
from ..models import Account, User


class AccountService:
    """
    Service for managing account operations.

    Handles business logic for account creation, retrieval, updates,
    and user-account association operations.
    """

    def __init__(self, account_repository: AccountRepository):
        """
        Initialize service with repository.

        Args:
            account_repository: Repository for account database operations
        """
        self.account_repository = account_repository

    async def create_account(
        self,
        name: str,
        account_type: str,
        owner_user_id: Optional[uuid.UUID] = None,
        business_id: Optional[str] = None,
    ) -> Account:
        """
        Create a new account.

        Args:
            name: Business name
            account_type: Account type (supplier, seller, hybrid)
            owner_user_id: UUID of the owner user
            business_id: Business registration number

        Returns:
            Newly created Account instance

        Raises:
            ValueError: If account with name already exists
        """
        if name:
            existing_account = await self.account_repository.get_by_name(name)
            if existing_account:
                raise ValueError(f"Account with name {name} already exists")

        account_data: Dict[str, Any] = {
            "business_name": name,
            "account_type": account_type,
        }

        if owner_user_id:
            account_data["owner_user_id"] = owner_user_id

        if business_id:
            account_data["business_id"] = business_id

        return await self.account_repository.create(account_data)

    async def get_account(self, account_id: uuid.UUID) -> Optional[Account]:
        """
        Get account by ID.

        Args:
            account_id: Account UUID

        Returns:
            Account instance if found, None otherwise
        """
        return await self.account_repository.get_by_id(account_id)

    async def get_account_by_name(self, name: str) -> Optional[Account]:
        """
        Get account by business name.

        Args:
            name: Business name

        Returns:
            Account instance if found, None otherwise
        """
        return await self.account_repository.get_by_name(name)

    async def update_account(
        self, account_id: uuid.UUID, data: Dict[str, Any]
    ) -> Optional[Account]:
        """
        Update account fields.

        Args:
            account_id: Account UUID
            data: Dictionary containing fields to update

        Returns:
            Updated Account instance if found, None otherwise
        """
        return await self.account_repository.update(account_id, data)

    async def get_account_users(self, account_id: uuid.UUID) -> List[User]:
        """
        Get all users for an account.

        Args:
            account_id: Account UUID

        Returns:
            List of User instances belonging to the account
        """
        return await self.account_repository.get_users(account_id)

    async def add_user_to_account(
        self, account_id: uuid.UUID, user_id: uuid.UUID, role: Optional[str] = None
    ) -> Account:
        """
        Add a user to an account (as owner).

        Args:
            account_id: Account UUID
            user_id: User UUID to add
            role: Optional role for the user (not used in current implementation)

        Returns:
            Updated Account instance

        Raises:
            ValueError: If account or user not found
        """
        account = await self.account_repository.get_by_id(account_id)
        if not account:
            raise ValueError("Account not found")

        account = await self.account_repository.update(
            account_id, {"owner_user_id": user_id}
        )

        return account

    async def remove_user_from_account(
        self, account_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        """
        Remove a user from an account.

        Args:
            account_id: Account UUID
            user_id: User UUID to remove

        Returns:
            True if user was removed, False otherwise

        Raises:
            ValueError: If account not found
        """
        account = await self.account_repository.get_by_id(account_id)
        if not account:
            raise ValueError("Account not found")

        if account.owner_user_id != user_id:
            return False

        await self.account_repository.update(account_id, {"owner_user_id": None})
        return True
