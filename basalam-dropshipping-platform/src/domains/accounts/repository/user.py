"""
User Repository
===============
Repository for User model operations
"""

from typing import Optional
import uuid
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import User


class UserRepository:
    """
    Repository for managing User entities.

    Handles database operations for user accounts
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize repository with database session.

        Args:
            session: Async SQLAlchemy session
        """
        self.session = session

    async def get_by_id(self, id: uuid.UUID) -> Optional[User]:
        """
        Get user by its UUID.

        Args:
            id: User UUID

        Returns:
            User instance if found, None otherwise
        """
        result = await self.session.execute(select(User).where(User.id == id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[User]:
        """
        Get user by email address.

        Args:
            email: User email address

        Returns:
            User instance if found, None otherwise
        """
        result = await self.session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_by_phone(self, phone: str) -> Optional[User]:
        """
        Get user by phone number.

        Args:
            phone: User phone number

        Returns:
            User instance if found, None otherwise
        """
        result = await self.session.execute(select(User).where(User.phone == phone))
        return result.scalar_one_or_none()

    async def create(self, data: dict) -> User:
        """
        Create a new user.

        Args:
            data: Dictionary containing user fields

        Returns:
            Newly created User instance
        """
        user = User(**data)
        self.session.add(user)
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def update(self, id: uuid.UUID, data: dict) -> Optional[User]:
        """
        Update user fields.

        Args:
            id: User UUID
            data: Dictionary containing fields to update

        Returns:
            Updated User instance if found, None otherwise
        """
        await self.session.execute(update(User).where(User.id == id).values(**data))
        await self.session.flush()
        return await self.get_by_id(id)

    async def delete(self, id: uuid.UUID) -> bool:
        """
        Delete a user by setting is_active to False.

        Args:
            id: User UUID

        Returns:
            True if user was deactivated, False if not found
        """
        result = await self.session.execute(
            update(User).where(User.id == id).values(is_active=False)
        )
        await self.session.flush()
        return result.rowcount > 0
