"""
API Dependencies
================
Common FastAPI dependencies for dependency injection
"""

from typing import Optional, AsyncGenerator
from uuid import UUID

import redis.asyncio as redis
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.core.config import get_settings
from src.core.database import async_session_maker
from src.core.events.publisher import EventPublisher
from src.domains.accounts.models import User
from src.domains.accounts.repository.account import AccountRepository
from src.domains.shops.repository.shop import ShopRepository
from src.domains.audit_logs.service import AuditLogService


SECRET_KEY = get_settings().secret_key.get_secret_value()
ALGORITHM = get_settings().jwt_algorithm

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
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


def decode_token(token: str) -> dict:
    """Decode and validate JWT token"""
    import jwt

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)
) -> User:
    """Get current authenticated user from token"""
    payload = decode_token(token)

    # Validate token type — reject refresh tokens used as access tokens
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload"
        )

    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive"
        )

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Get current active user"""
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


async def get_redis() -> Optional[redis.Redis]:
    """Get shared Redis client (singleton via core module)"""
    import structlog

    logger = structlog.get_logger(__name__)
    from src.core.redis_client import get_redis_client
    try:
        client = await get_redis_client()
        yield client
    except Exception as e:
        logger.warning("redis_unavailable", error=str(e))
        yield None


def require_role(*roles: str):
    """Dependency to require specific roles"""

    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
            )
        return current_user

    return role_checker


# ---- Admin Dependency ----

require_admin = require_role("admin")


# ---- AuditLog Dependency ----


async def get_audit_service(
    db: AsyncSession = Depends(get_db),
) -> AuditLogService:
    """Dependency to get an AuditLogService instance."""
    return AuditLogService(db)


# ---- Ownership Dependencies ----


async def verify_account_ownership(
    account_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Verify the account belongs to the current user."""
    repo = AccountRepository(db)
    account = await repo.get_by_id_and_owner(account_id, current_user.id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account not owned by current user",
        )
    return account


async def verify_shop_ownership(
    shop_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Verify the shop belongs to an account owned by the current user."""
    repo = ShopRepository(db)
    shop = await repo.get_by_id_and_owner(shop_id, current_user.id)
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    return shop


async def get_event_publisher(request: Request) -> EventPublisher:
    """Get the app-level EventPublisher instance."""
    return request.app.state.event_publisher
