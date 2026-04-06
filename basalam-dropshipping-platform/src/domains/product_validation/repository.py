"""
Product Validation Repository
============================
Database access for product validation log entries.
"""
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import ProductValidationLog


class ProductValidationRepository:
    """Repository for product validation log persistence."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, log_id: UUID) -> Optional[ProductValidationLog]:
        """Get a validation log by ID."""
        result = await self.session.execute(
            select(ProductValidationLog).where(ProductValidationLog.id == log_id)
        )
        return result.scalar_one_or_none()

    async def get_by_product(
        self, supplier_product_id: UUID, limit: int = 50
    ) -> List[ProductValidationLog]:
        """Get validation logs for a specific product."""
        stmt = (
            select(ProductValidationLog)
            .where(ProductValidationLog.supplier_product_id == supplier_product_id)
            .order_by(ProductValidationLog.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_for_product(
        self,
        supplier_product_id: UUID,
        validation_type: Optional[str] = None,
    ) -> Optional[ProductValidationLog]:
        """Get the most recent validation for a product."""
        stmt = (
            select(ProductValidationLog)
            .where(ProductValidationLog.supplier_product_id == supplier_product_id)
        )
        if validation_type:
            stmt = stmt.where(
                ProductValidationLog.validation_type == validation_type
            )
        stmt = stmt.order_by(ProductValidationLog.created_at.desc()).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_failures(
        self,
        supplier_product_id: Optional[UUID] = None,
        limit: int = 50,
    ) -> List[ProductValidationLog]:
        """Get failed validation logs."""
        stmt = select(ProductValidationLog).where(
            ProductValidationLog.status == "failed"
        )
        if supplier_product_id:
            stmt = stmt.where(
                ProductValidationLog.supplier_product_id == supplier_product_id
            )
        stmt = stmt.order_by(ProductValidationLog.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, data: dict) -> ProductValidationLog:
        """Create a new validation log entry."""
        entry = ProductValidationLog(**data)
        self.session.add(entry)
        await self.session.flush()
        await self.session.refresh(entry)
        return entry
