from typing import Optional, Type, TypeVar, Generic
import structlog
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession

from .base import BaseRepository

logger = structlog.get_logger(__name__)

T = TypeVar('T')


class UnitOfWork:
    """
    Unit of Work pattern implementation for managing database transactions.
    
    Provides:
    - Context manager for automatic commit/rollback
    - Repository integration
    - Proper error handling
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self._accounts = None
        self._shops = None
        self._products = None
        self._orders = None
        self._payments = None
        self._inventory = None
        self._webhooks = None
        self._notifications = None
    
    @property
    def accounts(self) -> BaseRepository:
        if self._accounts is None:
            from src.domains.accounts.models import Account
            self._accounts = BaseRepository(self.session, Account)
        return self._accounts
    
    @property
    def shops(self) -> BaseRepository:
        if self._shops is None:
            from src.domains.shops.models import Shop
            self._shops = BaseRepository(self.session, Shop)
        return self._shops
    
    @property
    def products(self) -> BaseRepository:
        if self._products is None:
            from src.domains.products.models import SupplierProduct
            self._products = BaseRepository(self.session, SupplierProduct)
        return self._products
    
    @property
    def orders(self) -> BaseRepository:
        if self._orders is None:
            from src.domains.orders.models import Order
            self._orders = BaseRepository(self.session, Order)
        return self._orders
    
    @property
    def payments(self) -> BaseRepository:
        if self._payments is None:
            from src.domains.payments.models import Payment
            self._payments = BaseRepository(self.session, Payment)
        return self._payments
    
    @property
    def inventory(self) -> BaseRepository:
        if self._inventory is None:
            from src.domains.inventory.models import InventoryReservation
            self._inventory = BaseRepository(self.session, InventoryReservation)
        return self._inventory
    
    @property
    def webhooks(self) -> BaseRepository:
        if self._webhooks is None:
            from src.domains.webhooks.models import WebhookEvent
            self._webhooks = BaseRepository(self.session, WebhookEvent)
        return self._webhooks
    
    @property
    def notifications(self) -> BaseRepository:
        if self._notifications is None:
            from src.domains.notifications.models import Notification
            self._notifications = BaseRepository(self.session, Notification)
        return self._notifications

    async def __aenter__(self) -> "UnitOfWork":
        """Enter the async context manager."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit the async context manager with proper error handling.

        Manages transaction boundary only (commit/rollback).
        Session lifecycle is owned by the caller (e.g. get_db dependency).
        """
        if exc_type is not None:
            await self.rollback()
            logger.error(
                "UnitOfWork rollback due to exception",
                exc_info=(exc_type, exc_val, exc_tb)
            )
            return False
        else:
            await self.commit()
        return True

    async def commit(self):
        """Commit the current transaction."""
        try:
            await self.session.commit()
            logger.debug("UnitOfWork commit successful")
        except Exception as e:
            logger.error("unitofwork_commit_failed", error=str(e))
            await self.session.rollback()
            raise

    async def rollback(self):
        """Rollback the current transaction."""
        try:
            await self.session.rollback()
            logger.debug("UnitOfWork rollback successful")
        except Exception as e:
            logger.error("unitofwork_rollback_failed", error=str(e))
            # Force close on rollback failure
            await self.session.close()
            raise

    async def flush(self):
        """Flush pending changes to the database."""
        await self.session.flush()

    async def refresh(self, instance):
        """Refresh an instance from the database."""
        await self.session.refresh(instance)


@asynccontextmanager
async def create_unit_of_work(session: AsyncSession):
    """
    Factory function to create and manage UnitOfWork.

    Usage:
        async with create_unit_of_work(session) as uow:
            await uow.accounts.create(...)
            # Automatic commit on success, rollback on failure

    Note: Session lifecycle is NOT managed here — the caller owns it.
    """
    uow = UnitOfWork(session)
    try:
        yield uow
        await uow.commit()
    except Exception:
        await uow.rollback()
        raise
