"""
Database Configuration
=====================
SQLAlchemy async configuration with PostgreSQL
"""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, DateTime, Uuid, MetaData
from datetime import datetime
import uuid

from src.core.config import get_settings

# Naming conventions ensure Alembic generates consistent, portable constraint
# names across all environments. Without this, names are auto-generated and
# differ between databases, causing migration failures.
NAMING_CONVENTION = {
    "ix": "ix__%(table_name)s__%(column_0_name)s",
    "uq": "uq__%(table_name)s__%(column_0_name)s",
    "ck": "ck__%(table_name)s__%(constraint_name)s",
    "fk": "fk__%(table_name)s__%(column_0_name)s__%(referred_table_name)s",
    "pk": "pk__%(table_name)s",
}

Base = declarative_base(metadata=MetaData(naming_convention=NAMING_CONVENTION))

DATABASE_URL = get_settings().database_url

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=20,
    max_overflow=40
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


class TimestampMixin:
    """Mixin for created_at and updated_at timestamps"""
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class UUIDMixin:
    """Mixin for UUID primary key"""
    id = Column(
        Uuid(as_uuid=True),
        primary_key=True, 
        default=uuid.uuid4,
        nullable=False
    )


async def get_db() -> AsyncSession:
    """Dependency for FastAPI to get database session"""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
