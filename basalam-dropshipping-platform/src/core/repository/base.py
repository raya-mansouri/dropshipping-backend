from typing import Generic, TypeVar, Optional, List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

Model = TypeVar("Model")


class BaseRepository(Generic[Model]):
    def __init__(self, session: AsyncSession, model: type[Model]):
        self.session = session
        self.model = model

    async def get_by_id(self, id: UUID) -> Optional[Model]:
        result = await self.session.get(self.model, id)
        return result

    async def get_all(self, skip: int = 0, limit: int = 100) -> List[Model]:
        from sqlalchemy import select

        result = await self.session.execute(
            select(self.model).offset(skip).limit(limit)
        )
        return list(result.scalars().all())

    async def create(self, data: dict) -> Model:
        instance = self.model(**data)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def update(self, id: UUID, data: dict) -> Optional[Model]:
        instance = await self.get_by_id(id)
        if instance is None:
            return None
        for key, value in data.items():
            setattr(instance, key, value)
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
