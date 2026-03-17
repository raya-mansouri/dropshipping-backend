"""
Platform Repository
==================
Repository for Platform model operations
"""

from typing import Optional, List
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import Base

from ..models import Platform


class PlatformRepository:
    """
    Repository for managing Platform entities.

    Handles database operations for platform records (Basalam, Shopify, etc.)
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize repository with database session.

        Args:
            session: Async SQLAlchemy session
        """
        self.session = session

    async def get_by_code(self, code: str) -> Optional[Platform]:
        """
        Get platform by its unique code.

        Args:
            code: Platform code (e.g., 'basalam', 'shopify', 'woocommerce')

        Returns:
            Platform instance if found, None otherwise
        """
        result = await self.session.execute(
            select(Platform).where(Platform.code == code)
        )
        return result.scalar_one_or_none()

    async def get_all(self) -> List[Platform]:
        """
        List all platforms.

        Returns:
            List of all Platform instances
        """
        result = await self.session.execute(select(Platform))
        return list(result.scalars().all())

    async def create(self, data: dict) -> Platform:
        """
        Create a new platform.

        Args:
            data: Dictionary containing platform fields

        Returns:
            Newly created Platform instance
        """
        platform = Platform(**data)
        self.session.add(platform)
        await self.session.flush()
        await self.session.refresh(platform)
        return platform
