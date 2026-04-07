"""
Auth API Endpoints
==================
FastAPI endpoints for authentication and user management
"""

from uuid import UUID
from typing import Optional
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

import structlog
from passlib.context import CryptContext

from src.api.deps import get_db, get_current_user, decode_token
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

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
logger = structlog.get_logger(__name__)


# ============================================
# Helper Functions
# ============================================


def hash_password(password: str) -> str:
    """Hash password using bcrypt"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against bcrypt hash"""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(user_id: UUID) -> str:
    """Create JWT access token"""
    import jwt

    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "type": "access", "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(user_id: UUID) -> str:
    """Create JWT refresh token"""
    import jwt

    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {"sub": str(user_id), "type": "refresh", "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


# ============================================
# API Router
# ============================================

router = APIRouter(prefix="/auth", tags=["auth"])


# ---- Registration ----


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    """
    Register a new user using phone number

    Creates user account and returns access/refresh tokens
    """
    result = await db.execute(select(User).where(User.phone == user_data.phone))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Phone number already registered"
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
    await db.refresh(user)

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    return Token(access_token=access_token, refresh_token=refresh_token)


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
            status_code=status.HTTP_400_BAD_REQUEST, detail="Phone number already registered"
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
    refresh_data: RefreshTokenRequest, db: AsyncSession = Depends(get_db)
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

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    return Token(access_token=access_token, refresh_token=refresh_token)


# ---- Logout ----


@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user)):
    """
    Logout (invalidate tokens client-side)
    """
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
    reset_data: PasswordResetRequest, db: AsyncSession = Depends(get_db)
):
    """
    Request password reset using phone number

    Generates a short-lived reset token. In production, send via SMS.
    """
    is_valid, error = validate_iranian_phone(reset_data.phone)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error
        )
    
    result = await db.execute(select(User).where(User.phone == reset_data.phone))
    user = result.scalar_one_or_none()

    if user:
        import jwt as jwt_module

        # Create a short-lived reset token (10 minutes)
        reset_expire = datetime.now(timezone.utc) + timedelta(minutes=10)
        reset_payload = {
            "sub": str(user.id),
            "phone": user.phone,
            "type": "password_reset",
            "exp": reset_expire,
        }
        _reset_token = jwt_module.encode(  # noqa: F841 — TODO: send via SMS
            reset_payload, SECRET_KEY, algorithm=ALGORITHM
        )
        # In production: send SMS with reset code to phone number
        # TODO: Store reset_token in Redis with TTL and send via SMS
        logger.info("password_reset_requested", user_id=str(user.id))

    # Always return success message for security (don't reveal if phone exists)
    return {"message": "If the phone number exists, a reset code has been sent"}


class PasswordResetConfirmRequest(BaseModel):
    reset_token: str
    new_password: str = Field(..., min_length=8)


@router.post("/reset-password")
async def reset_password(
    reset_data: PasswordResetConfirmRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Reset password using token

    Validates the reset token from forgot-password flow and updates the password.
    """
    # Decode the reset token to get the phone number
    payload = decode_token(reset_data.reset_token)
    phone = payload.get("phone")
    token_type = payload.get("type")

    if not phone or token_type != "password_reset":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    result = await db.execute(select(User).where(User.phone == phone))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    user.password_hash = hash_password(reset_data.new_password)
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
