"""
Accounts Domain Schemas
======================
Pydantic schemas for accounts API
"""
from pydantic import BaseModel, Field, ConfigDict, field_validator
from uuid import UUID
from datetime import datetime
from typing import Optional
from enum import Enum
from src.core.validators.phone import validate_iranian_phone


# Enums
class AccountType(str, Enum):
    SUPPLIER = "supplier"
    SELLER = "seller"
    HYBRID = "hybrid"


class AccountStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CLOSED = "closed"


class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


# User Schemas
class UserBase(BaseModel):
    """Base user schema - phone is the only identifier"""
    phone: str
    full_name: Optional[str] = None


class UserCreate(UserBase):
    password: str = Field(..., min_length=8)
    
    @field_validator('phone')
    @classmethod
    def validate_phone(cls, v: str) -> str:
        """Validate Iranian phone number format"""
        is_valid, error = validate_iranian_phone(v)
        if not is_valid:
            raise ValueError(error)
        return v


class UserUpdate(BaseModel):
    phone: Optional[str] = None
    full_name: Optional[str] = None
    is_active: Optional[bool] = None
    
    @field_validator('phone')
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        """Validate Iranian phone number format if provided"""
        if v is None:
            return v
        is_valid, error = validate_iranian_phone(v)
        if not is_valid:
            raise ValueError(error)
        return v


class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    is_active: bool
    is_verified: bool
    role: UserRole
    created_at: datetime
    updated_at: datetime


# Account Schemas
class AccountBase(BaseModel):
    account_type: AccountType
    business_name: Optional[str] = None
    business_id: Optional[str] = None


class AccountCreate(AccountBase):
    owner_user_id: UUID


class AccountUpdate(BaseModel):
    business_name: Optional[str] = None
    business_id: Optional[str] = None
    status: Optional[AccountStatus] = None


class AccountResponse(AccountBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    owner_user_id: UUID
    status: AccountStatus
    created_at: datetime
    updated_at: datetime


# Auth Schemas
class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: Optional[UUID] = None


class LoginRequest(BaseModel):
    phone: str
    password: str
    
    @field_validator('phone')
    @classmethod
    def validate_phone(cls, v: str) -> str:
        """Validate Iranian phone number format"""
        is_valid, error = validate_iranian_phone(v)
        if not is_valid:
            raise ValueError(error)
        return v


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class PasswordResetRequest(BaseModel):
    """Password reset using phone number"""
    phone: str
    
    @field_validator('phone')
    @classmethod
    def validate_phone(cls, v: str) -> str:
        """Validate Iranian phone number format"""
        is_valid, error = validate_iranian_phone(v)
        if not is_valid:
            raise ValueError(error)
        return v


class PasswordResetConfirm(BaseModel):
    """Confirm password reset with new password"""
    phone: str
    new_password: str = Field(..., min_length=8)
    reset_token: str
    
    @field_validator('phone')
    @classmethod
    def validate_phone(cls, v: str) -> str:
        """Validate Iranian phone number format"""
        is_valid, error = validate_iranian_phone(v)
        if not is_valid:
            raise ValueError(error)
        return v
