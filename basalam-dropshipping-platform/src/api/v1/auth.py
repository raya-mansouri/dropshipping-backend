"""
Auth API Endpoints
==================
FastAPI endpoints for authentication and user management
"""

from uuid import UUID
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta
import hashlib
import secrets

from src.core.database import get_db
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
    UserRole,
)


# ============================================
# Configuration
# ============================================

SECRET_KEY = get_settings().secret_key.get_secret_value()
ALGORITHM = get_settings().jwt_algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = get_settings().access_token_expire_minutes
REFRESH_TOKEN_EXPIRE_DAYS = get_settings().refresh_token_expire_days

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


# ============================================
# Helper Functions
# ============================================


def hash_password(password: str) -> str:
    """Hash password using SHA256 (in production, use bcrypt)"""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash"""
    return hash_password(plain_password) == hashed_password


def create_access_token(user_id: UUID) -> str:
    """Create JWT access token"""
    import jwt

    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "type": "access", "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(user_id: UUID) -> str:
    """Create JWT refresh token"""
    import jwt

    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {"sub": str(user_id), "type": "refresh", "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


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


# ============================================
# API Router
# ============================================

router = APIRouter(prefix="/auth", tags=["auth"])


# ---- Registration ----


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    """
    Register a new user

    Creates user account and returns access/refresh tokens
    """
    result = await db.execute(select(User).where(User.email == user_data.email))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
        )

    user = User(
        email=user_data.email,
        password_hash=hash_password(user_data.password),
        full_name=user_data.full_name,
        phone=user_data.phone,
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
    result = await db.execute(select(User).where(User.email == user_data.email))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
        )

    user = User(
        email=user_data.email,
        password_hash=hash_password(user_data.password),
        full_name=user_data.full_name,
        phone=user_data.phone,
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
    Login with email and password

    Returns access and refresh tokens
    """
    result = await db.execute(select(User).where(User.email == login_data.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(login_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
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

    In production, you might want to blacklist the token
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

    if "email" in update_dict:
        result = await db.execute(
            select(User).where(
                User.email == update_dict["email"], User.id != current_user.id
            )
        )
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Email already in use")

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


class PasswordResetRequest(BaseModel):
    email: EmailStr


@router.post("/forgot-password")
async def forgot_password(
    reset_data: PasswordResetRequest, db: AsyncSession = Depends(get_db)
):
    """
    Request password reset

    In production, send reset email with token
    """
    result = await db.execute(select(User).where(User.email == reset_data.email))
    user = result.scalar_one_or_none()

    if user:
        reset_token = secrets.token_urlsafe(32)
        # In production: send email with reset link

    return {"message": "If the email exists, a reset link has been sent"}


class PasswordResetConfirmRequest(BaseModel):
    reset_token: str
    new_password: str = Field(..., min_length=8)


@router.post("/reset-password")
async def reset_password(reset_data: PasswordResetConfirmRequest):
    """
    Reset password using token

    In production: validate token and update password
    """
    # In production: validate token from email
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
