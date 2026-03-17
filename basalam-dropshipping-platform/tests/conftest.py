"""
Pytest Configuration and Fixtures
=================================
Common fixtures for testing
"""

import uuid
from datetime import datetime, timedelta
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.core.database import Base
from src.main import app


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create an event loop for the test session."""
    import asyncio

    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Create a mock database session."""
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.close = AsyncMock()
    session.add = MagicMock()
    session.query = MagicMock()
    return session


@pytest.fixture
def mock_async_session_maker(mock_db_session):
    """Create a mock async session maker."""
    maker = MagicMock()
    maker.return_value.__aenter__ = AsyncMock(return_value=mock_db_session)
    maker.return_value.__aexit__ = AsyncMock(return_value=None)
    return maker


@pytest.fixture
async def test_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session with in-memory SQLite."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session

    await engine.dispose()


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Create an async HTTP client for testing."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def sample_uuid() -> uuid.UUID:
    """Generate a sample UUID."""
    return uuid.uuid4()


@pytest.fixture
def sample_variant_id() -> uuid.UUID:
    """Generate a sample variant UUID."""
    return uuid.uuid4()


@pytest.fixture
def sample_order_id() -> uuid.UUID:
    """Generate a sample order UUID."""
    return uuid.uuid4()


@pytest.fixture
def sample_order_item_id() -> uuid.UUID:
    """Generate a sample order item UUID."""
    return uuid.uuid4()


@pytest.fixture
def sample_user_id() -> uuid.UUID:
    """Generate a sample user UUID."""
    return uuid.uuid4()


@pytest.fixture
def sample_integration_id() -> uuid.UUID:
    """Generate a sample integration UUID."""
    return uuid.uuid4()


@pytest.fixture
def mock_supplier_variant(sample_variant_id):
    """Create a mock supplier variant."""
    variant = MagicMock()
    variant.id = sample_variant_id
    variant.supplier_id = uuid.uuid4()
    variant.sku = "TEST-SKU-001"
    variant.name = "Test Product Variant"
    variant.price = 29.99
    variant.inventory = 100
    variant.reserved_inventory = 0
    return variant


@pytest.fixture
def mock_order_item(sample_order_item_id, sample_order_id, sample_variant_id):
    """Create a mock order item."""
    item = MagicMock()
    item.id = sample_order_item_id
    item.order_id = sample_order_id
    item.variant_id = sample_variant_id
    item.quantity = 2
    item.price = 29.99
    return item


@pytest.fixture
def mock_inventory_reservation(sample_variant_id, sample_order_item_id):
    """Create a mock inventory reservation."""
    reservation = MagicMock()
    reservation.id = uuid.uuid4()
    reservation.variant_id = sample_variant_id
    reservation.order_item_id = sample_order_item_id
    reservation.quantity = 5
    reservation.status = "reserved"
    reservation.expires_at = datetime.utcnow() + timedelta(minutes=30)
    reservation.released_at = None
    reservation.released_reason = None
    reservation.created_at = datetime.utcnow()
    reservation.updated_at = datetime.utcnow()
    return reservation


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    redis = MagicMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=1)
    redis.exists = AsyncMock(return_value=False)
    redis.expire = AsyncMock(return_value=True)
    return redis


@pytest.fixture
def mock_kafka_producer():
    """Create a mock Kafka producer."""
    producer = MagicMock()
    producer.send_and_wait = AsyncMock()
    producer.start = AsyncMock()
    producer.stop = AsyncMock()
    return producer
