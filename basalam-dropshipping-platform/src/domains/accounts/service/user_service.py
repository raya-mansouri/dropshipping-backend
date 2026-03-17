"""
User Service
============
Service layer for user management operations
"""

import uuid
from typing import Optional, Dict, Any
from datetime import datetime

import bcrypt

from ..repository import UserRepository
from ..models import User


class UserService:
    """
    Service for managing user operations.

    Handles business logic for user creation, retrieval, updates,
    and authentication operations.
    """

    def __init__(self, user_repository: UserRepository):
        """
        Initialize service with repository.

        Args:
            user_repository: Repository for user database operations
        """
        self.user_repository = user_repository

    @staticmethod
    def _hash_password(password: str) -> str:
        """
        Hash a plain text password using bcrypt.

        Args:
            password: Plain text password to hash

        Returns:
            Hashed password string
        """
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    @staticmethod
    def _verify_password_hash(password: str, password_hash: str) -> bool:
        """
        Verify a password against its hash.

        Args:
            password: Plain text password to verify
            password_hash: Stored password hash

        Returns:
            True if password matches, False otherwise
        """
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))

    async def create_user(
        self,
        email: str,
        phone: Optional[str],
        password: str,
        account_id: Optional[uuid.UUID],
        role: str = "user",
    ) -> User:
        """
        Create a new user.

        Args:
            email: User email address
            phone: User phone number
            password: User plain text password
            account_id: Optional associated account UUID
            role: User role (user, admin, super_admin)

        Returns:
            Newly created User instance

        Raises:
            ValueError: If email already exists
        """
        existing_user = await self.user_repository.get_by_email(email)
        if existing_user:
            raise ValueError(f"User with email {email} already exists")

        password_hash = self._hash_password(password)

        user_data: Dict[str, Any] = {
            "email": email,
            "password_hash": password_hash,
            "role": role,
        }

        if phone:
            user_data["phone"] = phone

        user = await self.user_repository.create(user_data)

        return user

    async def get_user(self, user_id: uuid.UUID) -> Optional[User]:
        """
        Get user by ID.

        Args:
            user_id: User UUID

        Returns:
            User instance if found, None otherwise
        """
        return await self.user_repository.get_by_id(user_id)

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """
        Get user by email address.

        Args:
            email: User email address

        Returns:
            User instance if found, None otherwise
        """
        return await self.user_repository.get_by_email(email)

    async def update_user(
        self, user_id: uuid.UUID, data: Dict[str, Any]
    ) -> Optional[User]:
        """
        Update user fields.

        Args:
            user_id: User UUID
            data: Dictionary containing fields to update

        Returns:
            Updated User instance if found, None otherwise
        """
        if "password" in data:
            data["password_hash"] = self._hash_password(data.pop("password"))

        return await self.user_repository.update(user_id, data)

    async def delete_user(self, user_id: uuid.UUID) -> bool:
        """
        Delete (deactivate) a user.

        Args:
            user_id: User UUID

        Returns:
            True if user was deactivated, False if not found
        """
        return await self.user_repository.delete(user_id)

    async def verify_password(self, user_id: uuid.UUID, password: str) -> bool:
        """
        Verify user password.

        Args:
            user_id: User UUID
            password: Plain text password to verify

        Returns:
            True if password is correct, False otherwise
        """
        user = await self.user_repository.get_by_id(user_id)
        if not user:
            return False

        return self._verify_password_hash(password, user.password_hash)

    async def change_password(
        self, user_id: uuid.UUID, old_password: str, new_password: str
    ) -> bool:
        """
        Change user password.

        Args:
            user_id: User UUID
            old_password: Current password
            new_password: New password

        Returns:
            True if password was changed, False if old password is incorrect

        Raises:
            ValueError: If user not found
        """
        user = await self.user_repository.get_by_id(user_id)
        if not user:
            raise ValueError("User not found")

        if not self._verify_password_hash(old_password, user.password_hash):
            return False

        new_password_hash = self._hash_password(new_password)
        await self.user_repository.update(user_id, {"password_hash": new_password_hash})

        return True
