from typing import Generic, TypeVar, Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_

Model = TypeVar("Model")


class QueryBuilder(Generic[Model]):
    """Query builder for complex queries with filters, pagination, and ordering."""

    def __init__(self, session: AsyncSession, model: type[Model]):
        self.session = session
        self.model = model
        self._filters: List[Any] = []
        self._order_by: List[Any] = []
        self._limit_value: Optional[int] = None
        self._offset_value: Optional[int] = None

    def filter(self, *conditions) -> "QueryBuilder[Model]":
        """Add filter conditions."""
        self._filters.extend(conditions)
        return self

    def filter_by(self, **kwargs) -> "QueryBuilder[Model]":
        """Add filter conditions from keyword arguments."""
        for key, value in kwargs.items():
            if hasattr(self.model, key):
                self._filters.append(getattr(self.model, key) == value)
        return self

    def filter_or(self, **kwargs) -> "QueryBuilder[Model]":
        """Add OR filter conditions."""
        or_conditions = []
        for key, value in kwargs.items():
            if hasattr(self.model, key):
                or_conditions.append(getattr(self.model, key) == value)
        if or_conditions:
            self._filters.append(or_(*or_conditions))
        return self

    def order_by(self, *columns, ascending: bool = True) -> "QueryBuilder[Model]":
        """Add ordering."""
        for col in columns:
            if hasattr(self.model, col):
                order_col = getattr(self.model, col)
                if not ascending:
                    order_col = order_col.desc()
                self._order_by.append(order_col)
        return self

    def order_by_desc(self, *columns) -> "QueryBuilder[Model]":
        """Add descending order."""
        return self.order_by(*columns, ascending=False)

    def limit(self, value: int) -> "QueryBuilder[Model]":
        """Set limit."""
        self._limit_value = value
        return self

    def offset(self, value: int) -> "QueryBuilder[Model]":
        """Set offset."""
        self._offset_value = value
        return self

    async def execute(self) -> List[Model]:
        """Execute the query and return results."""
        stmt = select(self.model)

        if self._filters:
            stmt = stmt.where(and_(*self._filters))

        if self._order_by:
            stmt = stmt.order_by(*self._order_by)

        if self._limit_value is not None:
            stmt = stmt.limit(self._limit_value)

        if self._offset_value is not None:
            stmt = stmt.offset(self._offset_value)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count(self) -> int:
        """Count matching records."""
        stmt = select(func.count()).select_from(self.model)

        if self._filters:
            stmt = stmt.where(and_(*self._filters))

        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def first(self) -> Optional[Model]:
        """Get first result."""
        self._limit_value = 1
        results = await self.execute()
        return results[0] if results else None

    async def exists(self) -> bool:
        """Check if any records match."""
        return await self.count() > 0


class BaseRepository(Generic[Model]):
    """Base repository with CRUD operations, query builder, soft delete, and audit trail."""

    def __init__(self, session: AsyncSession, model: type[Model]):
        self.session = session
        self.model = model
        self._soft_delete_column = getattr(model, "deleted_at", None)

    def query(self) -> QueryBuilder[Model]:
        """Create a new query builder instance."""
        return QueryBuilder(self.session, self.model)

    async def get_by_id(
        self, id: UUID, include_deleted: bool = False
    ) -> Optional[Model]:
        """Get model by ID with optional soft delete handling."""
        stmt = select(self.model).where(self.model.id == id)
        if not include_deleted and self._soft_delete_column is not None:
            stmt = stmt.where(self._soft_delete_column.is_(None))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(
        self, skip: int = 0, limit: int = 100, include_deleted: bool = False
    ) -> List[Model]:
        """Get all models with optional soft delete handling."""
        from sqlalchemy import select

        stmt = select(self.model).offset(skip).limit(limit)
        if not include_deleted and self._soft_delete_column is not None:
            stmt = stmt.where(self._soft_delete_column.is_(None))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self,
        data: dict,
        created_by: Optional[UUID] = None,
    ) -> Model:
        """Create a new record with optional audit trail."""
        if created_by and hasattr(self.model, "created_by"):
            data["created_by"] = created_by
        if created_by and hasattr(self.model, "updated_by"):
            data["updated_by"] = created_by

        instance = self.model(**data)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def update(
        self,
        id: UUID,
        data: dict,
        updated_by: Optional[UUID] = None,
    ) -> Optional[Model]:
        """Update a record with optional audit trail."""
        instance = await self.get_by_id(id, include_deleted=True)
        if instance is None:
            return None

        for key, value in data.items():
            setattr(instance, key, value)

        if updated_by and hasattr(instance, "updated_by"):
            setattr(instance, "updated_by", updated_by)

        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def delete(self, id: UUID) -> bool:
        instance = await self.get_by_id(id)
        if instance is None:
            return False
        await self.session.delete(instance)
        await self.session.flush()
        return True

    async def exists(self, id: UUID) -> bool:
        instance = await self.get_by_id(id)
        return instance is not None

    async def count(self) -> int:
        from sqlalchemy import select, func

        result = await self.session.execute(
            select(func.count()).select_from(self.model)
        )
        return result.scalar() or 0

    async def soft_delete(self, id: UUID, deleted_by: Optional[UUID] = None) -> bool:
        """Soft delete a record by setting deleted_at timestamp."""
        if self._soft_delete_column is None:
            return await self.delete(id)

        instance = await self.get_by_id(id, include_deleted=True)
        if instance is None:
            return False

        setattr(instance, "deleted_at", datetime.utcnow())
        if hasattr(instance, "updated_by") and deleted_by:
            setattr(instance, "updated_by", deleted_by)

        await self.session.flush()
        return True

    async def restore(self, id: UUID, restored_by: Optional[UUID] = None) -> bool:
        """Restore a soft-deleted record."""
        if self._soft_delete_column is None:
            return False

        instance = await self.get_by_id(id, include_deleted=True)
        if instance is None:
            return False

        setattr(instance, "deleted_at", None)
        if hasattr(instance, "updated_by") and restored_by:
            setattr(instance, "updated_by", restored_by)

        await self.session.flush()
        return True

    async def list_with_filters(
        self,
        filters: Optional[Dict[str, Any]] = None,
        order_by: Optional[str] = None,
        ascending: bool = True,
        skip: int = 0,
        limit: int = 100,
        include_deleted: bool = False,
    ) -> List[Model]:
        """List records with filters, ordering, and pagination."""
        query = self.query()

        if filters:
            query = query.filter_by(**filters)

        if order_by and hasattr(self.model, order_by):
            if ascending:
                query = query.order_by(order_by)
            else:
                query = query.order_by_desc(order_by)

        if not include_deleted and self._soft_delete_column is not None:
            query = query.filter(self._soft_delete_column.is_(None))

        return await query.offset(skip).limit(limit).execute()

    async def count_with_filters(
        self,
        filters: Optional[Dict[str, Any]] = None,
        include_deleted: bool = False,
    ) -> int:
        """Count records with optional filters."""
        query = self.query()

        if filters:
            query = query.filter_by(**filters)

        if not include_deleted and self._soft_delete_column is not None:
            query = query.filter(self._soft_delete_column.is_(None))

        return await query.count()
