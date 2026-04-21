"""
Platform Repository
==================
Repository for Platform model operations, extending BaseRepository.
"""

from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repository.base import BaseRepository
from ..models import Platform


class PlatformRepository(BaseRepository[Platform]):
    """
    Repository for managing Platform entities.

    Extends BaseRepository for CRUD, QueryBuilder, pagination, and audit trail.
    """

    def __init__(self, session: AsyncSession):
        super().__init__(session, Platform)

    async def get_by_code(self, code: str) -> Optional[Platform]:
        """Get platform by its unique code (e.g., 'basalam', 'shopify')."""
        result = await self.session.execute(
            select(Platform).where(Platform.code == code)
        )
        return result.scalar_one_or_none()
