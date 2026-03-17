"""
Category Repository
====================
Repository for Category model operations
"""

from typing import Optional, List
import uuid
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Category


class CategoryRepository:
    """
    Repository for managing Category entities.

    Handles database operations for product categories
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize repository with database session.

        Args:
            session: Async SQLAlchemy session
        """
        self.session = session

    async def get_by_id(self, id: uuid.UUID) -> Optional[Category]:
        """
        Get category by its UUID.

        Args:
            id: Category UUID

        Returns:
            Category instance if found, None otherwise
        """
        result = await self.session.execute(select(Category).where(Category.id == id))
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> Optional[Category]:
        """
        Get category by external category ID.

        Args:
            code: External category ID (Basalam category ID)

        Returns:
            Category instance if found, None otherwise
        """
        result = await self.session.execute(
            select(Category).where(Category.external_category_id == code)
        )
        return result.scalar_one_or_none()

    async def get_root_categories(self) -> List[Category]:
        """
        Get all root-level categories (categories without parent).

        Returns:
            List of root Category instances
        """
        result = await self.session.execute(
            select(Category).where(Category.parent_id == None)
        )
        return list(result.scalars().all())

    async def get_children(self, parent_id: uuid.UUID) -> List[Category]:
        """
        Get all subcategories for a given parent category.

        Args:
            parent_id: Parent category UUID

        Returns:
            List of child Category instances
        """
        result = await self.session.execute(
            select(Category).where(Category.parent_id == parent_id)
        )
        return list(result.scalars().all())

    async def create(self, data: dict) -> Category:
        """
        Create a new category.

        Args:
            data: Dictionary containing category fields

        Returns:
            Newly created Category instance
        """
        category = Category(**data)
        self.session.add(category)
        await self.session.flush()
        await self.session.refresh(category)
        return category

    async def update(self, id: uuid.UUID, data: dict) -> Optional[Category]:
        """
        Update category fields.

        Args:
            id: Category UUID
            data: Dictionary containing fields to update

        Returns:
            Updated Category instance if found, None otherwise
        """
        await self.session.execute(
            update(Category).where(Category.id == id).values(**data)
        )
        await self.session.flush()
        return await self.get_by_id(id)
