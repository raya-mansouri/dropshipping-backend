"""
Accounts Domain Schemas
======================
Pydantic schemas for accounts API
"""
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from uuid import UUID
from datetime import datetime
from typing import Optional, List
from enum import Enum


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
    email: EmailStr
    full_name: Optional[str] = None
    phone: Optional[str] = None


class UserCreate(UserBase):
    password: str = Field(..., min_length=8)


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None


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
    email: EmailStr
    password: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str
