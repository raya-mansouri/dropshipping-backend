"""
Account Repository
==================
Repository for Account model operations
"""

from typing import Optional, List
import uuid
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Account, User


class AccountRepository:
    """
    Repository for managing Account entities.

    Handles database operations for accounts (suppliers, sellers, hybrids)
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize repository with database session.

        Args:
            session: Async SQLAlchemy session
        """
        self.session = session

    async def get_by_id(self, id: uuid.UUID) -> Optional[Account]:
        """
        Get account by its UUID.

        Args:
            id: Account UUID

        Returns:
            Account instance if found, None otherwise
        """
        result = await self.session.execute(select(Account).where(Account.id == id))
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Optional[Account]:
        """
        Get account by business name.

        Args:
            name: Business name

        Returns:
            Account instance if found, None otherwise
        """
        result = await self.session.execute(
            select(Account).where(Account.business_name == name)
        )
        return result.scalar_one_or_none()

    async def create(self, data: dict) -> Account:
        """
        Create a new account.

        Args:
            data: Dictionary containing account fields

        Returns:
            Newly created Account instance
        """
        account = Account(**data)
        self.session.add(account)
        await self.session.flush()
        await self.session.refresh(account)
        return account

    async def update(self, id: uuid.UUID, data: dict) -> Optional[Account]:
        """
        Update account fields.

        Args:
            id: Account UUID
            data: Dictionary containing fields to update

        Returns:
            Updated Account instance if found, None otherwise
        """
        await self.session.execute(
            update(Account).where(Account.id == id).values(**data)
        )
        await self.session.flush()
        return await self.get_by_id(id)

    async def get_users(self, account_id: uuid.UUID) -> List[User]:
        """
        Get all users for an account.

        Args:
            account_id: Account UUID

        Returns:
            List of User instances belonging to the account
        """
        result = await self.session.execute(
            select(User)
            .join(Account, Account.owner_user_id == User.id)
            .where(Account.id == account_id)
        )
        return list(result.scalars().all())

    async def delete(self, id: uuid.UUID) -> bool:
        """
        Soft delete an account by setting status to 'closed'.

        Args:
            id: Account UUID

        Returns:
            True if account was closed, False if not found
        """
        result = await self.session.execute(
            update(Account).where(Account.id == id).values(status="closed")
        )
        await self.session.flush()
        return result.rowcount > 0
