from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from .base import BaseRepository


class UnitOfWork:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.accounts: Optional[BaseRepository] = None
        self.shops: Optional[BaseRepository] = None
        self.products: Optional[BaseRepository] = None
        self.orders: Optional[BaseRepository] = None
        self.payments: Optional[BaseRepository] = None
        self.inventory: Optional[BaseRepository] = None
        self.webhooks: Optional[BaseRepository] = None
        self.notifications: Optional[BaseRepository] = None

    async def __aenter__(self) -> "UnitOfWork":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            await self.rollback()
        else:
            await self.commit()
        await self.session.close()

    async def commit(self):
        await self.session.commit()

    async def rollback(self):
        await self.session.rollback()
