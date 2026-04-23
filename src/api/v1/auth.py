"""
Auth API Endpoints
==================
FastAPI endpoints for authentication and user management
"""

import random
from uuid import UUID, uuid4
from typing import Optional
from datetime import datetime, timedelta, timezone
from jose import jwt

from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import redis.asyncio as redis

import structlog
import bcrypt as _bcrypt
import httpx

from src.api.deps import get_db, get_current_user, decode_token, get_redis
from src.core.config import get_settings
from src.domains.accounts.models import User, Account
from src.domains.accounts.schemas import (
    UserResponse,
    UserCreate,
    UserUpdate,
    AccountResponse,
    AccountCreate,
    AccountUpdate,
    AccountType,
    AccountStatus,
    Token,
    LoginRequest,
    RefreshTokenRequest,
    PasswordResetRequest,
    UserRole,
)
from src.core.validators.phone import validate_iranian_phone


# ============================================
# Configuration
# ============================================

SECRET_KEY = get_settings().secret_key.get_secret_value()
ALGORITHM = get_settings().jwt_algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = get_settings().access_token_expire_minutes
REFRESH_TOKEN_EXPIRE_DAYS = get_settings().refresh_token_expire_days

logger = structlog.get_logger(__name__)


# ============================================
# Helper Functions
# ============================================


def hash_password(password: str) -> str:
    """Hash password using bcrypt directly"""
    return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against bcrypt hash. Returns False for invalid hashes."""
    try:
        return _bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )
    except (ValueError, TypeError):
        return False


async def blacklist_token(
    redis_client: redis.Redis, token_jti: str, exp: datetime
) -> None:
    """
    Add a token's JTI to the Redis blacklist with a TTL equal to remaining lifetime.

    The key expires automatically from Redis once the token's original expiry passes,
    so the blacklist does not grow unbounded.
    """
    now = datetime.now(timezone.utc)
    remaining_seconds = int((exp - now).total_seconds())
    if remaining_seconds > 0:
        await redis_client.set(
            f"blacklist:token:{token_jti}",
            "1",
            ex=remaining_seconds,
        )


def create_access_token(user_id: UUID) -> str:
    """Create JWT access token"""

    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "exp": expire,
        "jti": str(uuid4()),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(user_id: UUID) -> str:
    """Create JWT refresh token"""

    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "exp": expire,
        "jti": str(uuid4()),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


# ============================================
# API Router
# ============================================

router = APIRouter(prefix="/auth", tags=["auth"])


# ---- Registration ----


@router.post(
    "/register/with-account", response_model=dict, status_code=status.HTTP_201_CREATED
)
async def register_with_account(
    user_data: UserCreate,
    account_type: AccountType,
    business_name: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new user with an account

    Creates user, account, and returns tokens
    """
    result = await db.execute(select(User).where(User.phone == user_data.phone))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phone number already registered",
        )

    user = User(
        phone=user_data.phone,
        password_hash=hash_password(user_data.password),
        full_name=user_data.full_name,
        is_active=True,
        is_verified=False,
        role=UserRole.USER.value,
    )
    db.add(user)
    await db.flush()

    account = Account(
        owner_user_id=user.id,
        account_type=account_type.value,
        business_name=business_name,
        status=AccountStatus.ACTIVE.value,
    )
    db.add(account)
    await db.flush()
    await db.refresh(user)

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    return {
        "user": UserResponse.model_validate(user),
        "account": AccountResponse.model_validate(account),
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


# ---- Login ----


@router.post("/login", response_model=Token)
async def login(login_data: LoginRequest, db: AsyncSession = Depends(get_db)):
    """
    Login with phone number and password

    Returns access and refresh tokens
    """
    result = await db.execute(select(User).where(User.phone == login_data.phone))
    user = result.scalar_one_or_none()

    if not user or not verify_password(login_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect phone number or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive"
        )

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    return Token(access_token=access_token, refresh_token=refresh_token)


# ---- Token Refresh ----


@router.post("/refresh", response_model=Token)
async def refresh_token(
    refresh_data: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
):
    """
    Refresh access token using refresh token

    Returns new access and refresh tokens
    """
    payload = decode_token(refresh_data.refresh_token)

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type"
        )

    # Check if the refresh token has been blacklisted
    refresh_jti = payload.get("jti")
    if refresh_jti and await redis_client.get(f"blacklist:token:{refresh_jti}"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload"
        )

    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    # Blacklist the old refresh token so it cannot be reused
    old_exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    if refresh_jti:
        await blacklist_token(redis_client, refresh_jti, old_exp)

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    return Token(access_token=access_token, refresh_token=refresh_token)


# ---- Logout ----


@router.post("/logout")
async def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
    redis_client: redis.Redis = Depends(get_redis),
):
    """
    Logout (server-side token invalidation)

    Blacklists the current access token and optionally the refresh token
    from the request body. Blacklisted tokens are stored in Redis with a
    TTL equal to the token's remaining lifetime, so keys are cleaned up
    automatically once the token expires.
    """
    # --- Blacklist the access token from the Authorization header ---
    auth_header = request.headers.get("Authorization", "")
    access_token_str = auth_header.removeprefix("Bearer ").strip()
    access_payload = decode_token(access_token_str)

    access_jti = access_payload.get("jti")
    if access_jti:
        access_exp = datetime.fromtimestamp(access_payload["exp"], tz=timezone.utc)
        await blacklist_token(redis_client, access_jti, access_exp)

    # --- Optionally blacklist a refresh token sent in the body ---
    try:
        body = await request.json()
        refresh_token_str = body.get("refresh_token")
    except Exception:
        refresh_token_str = None

    if refresh_token_str:
        try:
            refresh_payload = decode_token(refresh_token_str)
            refresh_jti = refresh_payload.get("jti")
            if refresh_jti:
                refresh_exp = datetime.fromtimestamp(
                    refresh_payload["exp"], tz=timezone.utc
                )
                await blacklist_token(redis_client, refresh_jti, refresh_exp)
        except HTTPException:
            # If the refresh token is already expired or invalid, skip silently
            pass

    logger.info(
        "user_logout",
        user_id=str(current_user.id),
        access_jti=access_jti,
    )

    return {"message": "Successfully logged out"}


# ---- Current User ----


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current authenticated user info"""
    return current_user


@router.patch("/me", response_model=UserResponse)
async def update_current_user(
    user_data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update current user profile"""
    update_dict = user_data.model_dump(exclude_unset=True)

    # Check for duplicate phone
    if "phone" in update_dict and update_dict["phone"]:
        result = await db.execute(
            select(User).where(
                User.phone == update_dict["phone"], User.id != current_user.id
            )
        )
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Phone number already in use")

    for field, value in update_dict.items():
        setattr(current_user, field, value)

    await db.flush()
    await db.refresh(current_user)
    return current_user


# ---- Password Management ----


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)


@router.post("/change-password")
async def change_password(
    password_data: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change user password"""
    if not verify_password(password_data.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    current_user.password_hash = hash_password(password_data.new_password)
    await db.flush()

    return {"message": "Password changed successfully"}


@router.post("/forgot-password")
async def forgot_password(
    reset_data: PasswordResetRequest,
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
):
    """
    Request password reset using phone number.

    Generates a 6-digit OTP, stores it in Redis with 10 min TTL,
    and sends it via Kavenegar SMS.
    """
    is_valid, error = validate_iranian_phone(reset_data.phone)
    if not is_valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)

    # Rate limit: max 3 OTP requests per phone per 10 minutes
    rate_key = f"otp_request:{reset_data.phone}"
    count = await redis_client.incr(rate_key)
    if count == 1:
        await redis_client.expire(rate_key, 600)
    if count > 3:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Try again later.",
        )

    result = await db.execute(select(User).where(User.phone == reset_data.phone))
    user = result.scalar_one_or_none()

    if user:
        otp = f"{random.randint(100000, 999999)}"
        redis_key = f"password_reset:{reset_data.phone}"
        await redis_client.set(redis_key, otp, ex=600)

        settings = get_settings()
        if settings.kavenegar_api_key:
            try:
                async with httpx.AsyncClient() as client:
                    await client.post(
                        f"https://api.kavenegar.com/v1/{settings.kavenegar_api_key}/sms/send.json",
                        data={
                            "receptor": reset_data.phone,
                            "sender": settings.kavenegar_sender,
                            "message": f"کد بازیابی رمز عبور: {otp}\nاعتبار: ۱۰ دقیقه",
                        },
                        timeout=10,
                    )
                logger.info("password_reset_otp_sent", user_id=str(user.id))
            except Exception as exc:
                logger.error("password_reset_sms_failed", error=str(exc))
        else:
            logger.warning(
                "password_reset_otp_skipped_no_kavenegar",
                user_id=str(user.id),
                otp=otp,
            )

    return {"message": "If the phone number exists, a reset code has been sent"}


class PasswordResetConfirmRequest(BaseModel):
    phone: str
    otp: str
    new_password: str = Field(..., min_length=8)


@router.post("/reset-password")
async def reset_password(
    reset_data: PasswordResetConfirmRequest,
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
):
    """
    Reset password using OTP sent via SMS.

    Validates the OTP from Redis and updates the password.
    """
    # Rate limit: max 5 verification attempts per phone per 10 minutes
    rate_key = f"otp_verify:{reset_data.phone}"
    count = await redis_client.incr(rate_key)
    if count == 1:
        await redis_client.expire(rate_key, 600)
    if count > 5:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Try again later.",
        )

    redis_key = f"password_reset:{reset_data.phone}"
    stored_otp = await redis_client.get(redis_key)

    if not stored_otp or stored_otp != reset_data.otp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset code",
        )

    result = await db.execute(select(User).where(User.phone == reset_data.phone))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset code",
        )

    user.password_hash = hash_password(reset_data.new_password)
    await redis_client.delete(redis_key)
    # Clear rate-limit counters after successful reset
    await redis_client.delete(f"otp_request:{reset_data.phone}")
    await redis_client.delete(f"otp_verify:{reset_data.phone}")
    await db.flush()

    return {"message": "Password reset successfully"}


# ---- User Management (Admin) ----


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
    is_active: Optional[bool] = None,
    current_user: User = Depends(get_current_user),
):
    """List users (admin only)"""
    if current_user.role not in [UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required"
        )

    query = select(User)
    if is_active is not None:
        query = query.where(User.is_active == is_active)

    query = query.limit(limit).offset(offset).order_by(User.created_at.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get user by ID (admin only)"""
    if current_user.role not in [UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required"
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    user_data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update user (admin only)"""
    if current_user.role not in [UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required"
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    update_dict = user_data.model_dump(exclude_unset=True)

    # Validate role against UserRole enum to prevent privilege escalation
    if "role" in update_dict:
        valid_roles = [r.value for r in UserRole]
        if update_dict["role"] not in valid_roles:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid role. Must be one of: {valid_roles}",
            )

    for field, value in update_dict.items():
        setattr(user, field, value)

    await db.flush()
    await db.refresh(user)
    return user


# ---- Account Management ----


@router.post(
    "/accounts", response_model=AccountResponse, status_code=status.HTTP_201_CREATED
)
async def create_account(
    account_data: AccountCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new account for current user"""
    if account_data.owner_user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot create account for another user",
        )

    account = Account(**account_data.model_dump())
    db.add(account)
    await db.flush()
    await db.refresh(account)
    return account


@router.get("/accounts", response_model=list[AccountResponse])
async def list_accounts(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """List accounts for current user"""
    result = await db.execute(
        select(Account).where(Account.owner_user_id == current_user.id)
    )
    return result.scalars().all()


@router.get("/accounts/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get account by ID"""
    result = await db.execute(
        select(Account).where(
            Account.id == account_id, Account.owner_user_id == current_user.id
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@router.patch("/accounts/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: UUID,
    account_data: AccountUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update account"""
    result = await db.execute(
        select(Account).where(
            Account.id == account_id, Account.owner_user_id == current_user.id
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    update_dict = account_data.model_dump(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(account, field, value)

    await db.flush()
    await db.refresh(account)
    return account
